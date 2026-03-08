# Falco로 런타임 보안 감시 구축하기

> 2026.03.08

## 런타임 보안이 뭔가

K8s 보안을 크게 나누면 이렇다:

```
빌드 타임 보안: 이미지에 취약점이 있나? (Trivy 같은 도구)
배포 타임 보안: 설정이 안전한가? (Pod Security Standards, OPA)
런타임 보안: 실행 중에 이상한 행위가 있나? ← 이게 Falco가 하는 일
```

컨테이너가 정상적으로 빌드되고 배포됐더라도, 실행 중에 공격당할 수 있다. 예를 들면:
- 웹 취약점으로 컨테이너에 셸이 열림
- 공격자가 추가 도구를 다운로드함
- /etc/shadow 같은 민감 파일을 읽음
- 리버스 셸로 외부 서버와 연결

이런 걸 **실시간으로** 잡아내는 게 Falco다.

---

## Falco가 어떻게 동작하나

Falco는 리눅스 커널 레벨에서 시스템 콜(syscall)을 감시한다.

```
[컨테이너에서 cat /etc/shadow 실행]
        ↓
[커널에서 openat() syscall 발생]
        ↓
[Falco의 eBPF 프로브가 이 syscall을 캐치]
        ↓
[룰 엔진에서 "민감 파일 접근" 룰에 매칭]
        ↓
[경고 출력 → Falcosidekick으로 전달 → 웹 UI, Slack 등으로 알림]
```

핵심은 **eBPF(extended Berkeley Packet Filter)**다. 커널에 모듈을 따로 설치하지 않고도 syscall을 가로챌 수 있는 기술이다. 성능 오버헤드도 거의 없다.

### Falco 구성 요소

| 컴포넌트 | 역할 |
|---|---|
| Falco (DaemonSet) | 각 노드에서 syscall 감시, 룰 매칭 |
| Falcosidekick | Falco 이벤트를 Slack, 웹훅 등으로 전달 |
| Falcosidekick UI | 웹 브라우저에서 이벤트 확인 |

DaemonSet이라서 모든 노드에 하나씩 떠있다. 내 클러스터에서는 3개 (CP 1 + Worker 2).

---

## ArgoCD로 Falco 배포하기

이전에 ArgoCD를 세팅해뒀으니, Falco도 ArgoCD로 배포했다. Helm 차트를 직접 참조하는 방식이다.

### sample-nginx vs Falco 배포 방식 차이

```
sample-nginx: GitHub 레포의 YAML 감시 → push하면 배포
Falco: Falco 공식 Helm 레포에서 차트 다운로드 → ArgoCD가 설치
```

ArgoCD는 두 가지 소스를 지원한다:
1. **Git 레포** — YAML 파일을 직접 관리할 때
2. **Helm 차트 레포** — 외부 차트를 가져올 때

Falco는 공식 Helm 차트가 잘 되어 있어서 2번 방식을 썼다.

### ArgoCD Application 설정

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: falco
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://falcosecurity.github.io/charts   # Falco 공식 Helm 레포
    chart: falco
    targetRevision: 4.*                                 # 4.x 최신 버전 자동
    helm:
      values: |
        driver:
          kind: modern_ebpf        # Kind(Docker) 호환 드라이버
        tty: true
        falcosidekick:
          enabled: true
          webui:
            enabled: true
        customRules:               # 커스텀 탐지 룰
          custom-rules.yaml: |-
            # ... (아래에서 설명)
  destination:
    server: https://kubernetes.default.svc
    namespace: falco
  syncPolicy:
    automated:
      selfHeal: true
      prune: true
    syncOptions:
      - CreateNamespace=true
```

포인트:
- `driver.kind: modern_ebpf` — Kind 환경에서는 커널 모듈 방식이 안 돼서 modern eBPF를 써야 한다
- `falcosidekick.enabled: true` — 이벤트 전달 + 웹 UI 활성화
- `syncPolicy.automated` — Git과 동기화 자동, 수동 개입 불필요

### 적용

```bash
kubectl apply -f argocd/falco-app.yaml
```

ArgoCD가 알아서 Helm 차트를 받아서 설치한다. `kubectl get application -n argocd`로 확인하면:

```
NAME           SYNC STATUS   HEALTH STATUS
falco          Synced        Healthy
sample-nginx   Synced        Healthy
```

### 설치된 Pod 확인

```bash
kubectl get pods -n falco
```

```
NAME                                     READY   STATUS    AGE
falco-xxxxx                              2/2     Running   (각 노드마다 1개, 총 3개)
falco-falcosidekick-xxxxx                1/1     Running   (이벤트 전달, 2개)
falco-falcosidekick-ui-xxxxx             1/1     Running   (웹 UI, 2개)
falco-falcosidekick-ui-redis-0           1/1     Running   (UI 데이터 저장, 1개)
```

총 8개 Pod가 뜬다.

---

## 기본 탐지 테스트

설치하고 나면 당연히 테스트를 해봐야 한다. nginx 컨테이너에 들어가서 민감 파일을 읽어봤다.

```bash
kubectl exec -it <nginx-pod> -- /bin/sh -c "cat /etc/shadow"
```

Falco 로그를 확인하면:

```json
{
  "rule": "Read sensitive file untrusted",
  "priority": "Warning",
  "output": "Sensitive file opened for reading by non-trusted program |
    file=/etc/shadow
    process=cat
    command=cat /etc/shadow
    user=root
    container_image=docker.io/library/nginx:1.27-alpine
    k8s_pod_name=sample-nginx-xxx",
  "tags": ["T1555", "mitre_credential_access"]
}
```

Falco 기본 룰이 `/etc/shadow` 접근을 바로 잡아냈다. MITRE ATT&CK T1555(Credential Access) 태그까지 달린다.

---

## 커스텀 룰 작성

기본 룰만으로도 많은 걸 잡아내지만, 실무에서는 환경에 맞는 커스텀 룰이 필요하다. 5개를 만들어봤다.

### 룰 1: 컨테이너에서 셸 실행 탐지

```yaml
- rule: Shell spawned in container
  condition: >
    spawned_process and container and
    proc.name in (bash, sh, zsh, ash)
  priority: WARNING
```

운영 환경에서 컨테이너 안에 직접 셸로 접속하는 건 거의 없어야 정상이다. 이게 뜨면 누군가 `kubectl exec`을 했거나, 더 나쁜 경우 공격자가 셸을 얻은 거다.

### 룰 2: 패키지 매니저 실행 탐지

```yaml
- rule: Package manager in container
  condition: >
    spawned_process and container and
    proc.name in (apt, apt-get, yum, dnf, apk, pip, npm)
  priority: WARNING
```

컨테이너에서 패키지를 설치한다? 공격자가 추가 도구를 설치하려는 시도일 가능성이 높다.

### 룰 3: 네트워크 도구 실행 탐지

```yaml
- rule: Network tool in container
  condition: >
    spawned_process and container and
    proc.name in (curl, wget, nc, ncat, nmap)
  priority: WARNING
```

외부에서 스크립트를 다운로드하거나, 포트 스캐닝을 시도하는 행위를 잡는다.

### 룰 4: 민감 파일 수정 탐지 (CRITICAL)

```yaml
- rule: Sensitive file modification
  condition: >
    open_write and container and
    fd.name in (/etc/passwd, /etc/shadow, /etc/sudoers)
  priority: CRITICAL
```

읽는 것도 위험하지만, 쓰는 건 더 위험하다. 백도어 계정을 만들려는 시도일 수 있다.

### 룰 5: 리버스 셸 탐지 (CRITICAL)

```yaml
- rule: Reverse shell in container
  condition: >
    spawned_process and container and
    ((proc.name = bash and proc.args contains "/dev/tcp") or
     (proc.name in (nc, ncat) and proc.args contains "-e"))
  priority: CRITICAL
```

리버스 셸은 공격자가 외부 서버로 연결하는 전형적인 수법이다. 이건 무조건 CRITICAL이다.

---

## 공격 시나리오 시뮬레이션 결과

커스텀 룰이 제대로 동작하는지 실제 공격 시나리오를 돌려봤다.

```bash
# 셸 접속
kubectl exec <pod> -- /bin/sh -c "echo shell-test"

# 패키지 매니저 실행
kubectl exec <pod> -- /bin/sh -c "apk --version"

# 외부 다운로드 시도
kubectl exec <pod> -- /bin/sh -c "wget --spider http://example.com"

# 민감 파일 읽기
kubectl exec <pod> -- /bin/sh -c "cat /etc/shadow"
```

### 탐지 결과

| 룰 | 탐지 횟수 | MITRE ATT&CK |
|---|---|---|
| Shell spawned in container | 9회 | Execution |
| Package manager in container | 3회 | Execution |
| Network tool in container | 3회 | Command & Control |
| Read sensitive file untrusted (기본 룰) | 1회 | Credential Access |

모든 공격이 빠짐없이 탐지됐다. 3개 노드 모두에서 이벤트가 올라오는 것도 확인했다.

---

## Falcosidekick UI

웹 UI로 이벤트를 시각적으로 확인할 수 있다.

```bash
# 포트포워딩
kubectl port-forward svc/falco-falcosidekick-ui -n falco 2802:2802

# http://localhost:2802 접속
```

이벤트를 심각도별로 필터링하거나, 시간대별로 확인할 수 있다. 대시보드에서 한눈에 상태를 파악할 수 있어서 좋다.

---

## Falco 룰 작성 문법

나중에 룰을 더 만들 때 참고할 내용.

### 기본 구조

```yaml
- rule: 룰 이름
  desc: 설명
  condition: 탐지 조건 (syscall 필터)
  output: 경고 메시지 (변수 사용 가능)
  priority: DEBUG/INFO/NOTICE/WARNING/ERROR/CRITICAL
  tags: [태그들]
```

### 자주 쓰는 조건

| 조건 | 의미 |
|---|---|
| `spawned_process` | 새 프로세스가 생성됨 |
| `container` | 컨테이너 안에서 발생 |
| `open_write` | 파일을 쓰기 모드로 열음 |
| `open_read` | 파일을 읽기 모드로 열음 |
| `proc.name` | 프로세스 이름 |
| `fd.name` | 파일/소켓 이름 |
| `k8s.pod.name` | Pod 이름 |
| `k8s.ns.name` | 네임스페이스 이름 |

### 출력에 쓸 수 있는 변수

| 변수 | 의미 |
|---|---|
| `%container.name` | 컨테이너 이름 |
| `%k8s.pod.name` | Pod 이름 |
| `%k8s.ns.name` | 네임스페이스 |
| `%proc.cmdline` | 실행된 명령어 전체 |
| `%user.name` | 실행한 사용자 |
| `%container.image.repository` | 컨테이너 이미지 |

---

## 현재 아키텍처

```
[Kind 클러스터]
├── Control Plane
│   └── Falco (DaemonSet) — syscall 감시
├── Worker 1
│   ├── Falco (DaemonSet)
│   ├── sample-nginx Pod
│   ├── Falcosidekick — 이벤트 전달
│   └── Falcosidekick UI — 웹 대시보드
├── Worker 2
│   ├── Falco (DaemonSet)
│   ├── sample-nginx Pod
│   └── Falcosidekick (replica)
└── ArgoCD — 모든 배포를 Git으로 관리
    ├── sample-nginx (Git 레포 감시)
    └── falco (Helm 차트 레포 참조)
```

## 다음에 할 것

- [ ] Trivy로 컨테이너 이미지 보안 스캔
- [ ] Falco 이벤트를 Slack/웹훅으로 자동 알림
- [ ] Prometheus + Grafana 모니터링 대시보드
- [ ] Python 앱 만들어서 전체 파이프라인 테스트
