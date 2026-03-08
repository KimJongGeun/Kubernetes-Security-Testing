# Docker로 로컬 Kubernetes 환경 구축하기

> 2026.03.08

## 시작하게 된 계기

K8s를 공부하려고 AWS EKS를 바로 써볼까 했는데, 잘 모르는 상태에서 클라우드 쓰면 요금 폭탄 맞을 것 같았다.
그래서 로컬에서 먼저 충분히 익히고 나서 클라우드로 넘어가기로 했다.

로컬에서 K8s를 돌리는 방법이 몇 가지 있어서 비교해봤다.

| 도구 | 특징 | 멀티노드 | 내가 느낀 점 |
|---|---|---|---|
| **Kind** | Docker 컨테이너가 곧 K8s 노드 | O | 가볍고 빠르다. 이걸로 결정 |
| k3d | k3s를 Docker에 올림 | O | 괜찮은데 K8s 일부 기능이 빠져있음 |
| Minikube | 가장 유명함 | 제한적 | 무겁고 느림. VM 기반이라 답답 |
| Docker Desktop K8s | 체크박스 하나로 켜짐 | X | 간편한데 싱글노드라 한계가 있음 |

Kind를 고른 이유는 간단하다. Docker만 있으면 되고, 클러스터 만드는 데 1분도 안 걸리고, 멀티노드도 설정 파일 몇 줄이면 된다. 무엇보다 실제 K8s랑 거의 똑같이 동작해서 학습용으로 딱이다.

---

## 1. 필요한 도구 설치

```bash
brew install kind kubectl helm k9s
```

각각 뭐 하는 도구인지 간단히 정리하면:

- **kind** — Docker 안에 K8s 클러스터를 만들어주는 도구
- **kubectl** — K8s 클러스터한테 명령을 내리는 CLI
- **helm** — K8s용 패키지 매니저. 복잡한 앱도 한 줄로 설치 가능
- **k9s** — 터미널에서 쓰는 K8s 대시보드. Pod 상태를 실시간으로 볼 수 있어서 편하다

---

## 2. 클러스터 설정

나는 실제 운영 환경이랑 비슷하게 구성하고 싶어서 노드를 3개로 나눴다.

```yaml
# k8s/kind-config.yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: local-k8s
nodes:
  - role: control-plane
    kubeadmConfigPatches:
      - |
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"
    extraPortMappings:
      - containerPort: 80
        hostPort: 80
        protocol: TCP
      - containerPort: 443
        hostPort: 443
        protocol: TCP
  - role: worker
  - role: worker
```

간단히 설명하면:

**Control Plane 1대 + Worker 2대** 구성이다.
Control Plane은 K8s의 두뇌 역할(스케줄링, 상태 관리)을 하고, Worker는 실제로 앱이 돌아가는 노드다.

Worker를 2대 둔 건 Pod가 여러 노드에 분산되는 걸 직접 보고 싶어서다. 싱글 노드로는 이게 확인이 안 된다.

`extraPortMappings`는 호스트의 80/443 포트를 클러스터에 연결하는 설정이다. 이게 있어야 나중에 `localhost`로 클러스터 안의 서비스에 접근할 수 있다.

### 클러스터 생성

```bash
kind create cluster --config k8s/kind-config.yaml
```

확인해보면 노드 3개가 잘 뜬 걸 볼 수 있다:

```
$ kubectl get nodes
NAME                      STATUS   ROLES           VERSION
local-k8s-control-plane   Ready    control-plane   v1.35.0
local-k8s-worker          Ready    <none>          v1.35.0
local-k8s-worker2         Ready    <none>          v1.35.0
```

---

## 3. Ingress Controller 설치

K8s 안의 서비스는 기본적으로 외부에서 접근이 안 된다. 그래서 Ingress Controller가 필요하다.
쉽게 말하면 외부 요청을 받아서 클러스터 안의 적절한 서비스로 보내주는 관문 같은 거다.

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
```

설치하고 나면 이런 흐름이 된다:

```
브라우저 → localhost:80 → Ingress Controller → Service → Pod
```

나중에 Ingress 규칙을 만들면 `/api`는 백엔드로, `/`는 프론트엔드로 라우팅하는 것도 가능하다.

---

## 4. 보안 설정

로컬이라도 보안 설정은 처음부터 하는 게 좋다고 생각한다. 나중에 운영 환경에서 "아 보안 설정 안 했네" 하고 뒤늦게 추가하면 빠지는 게 꼭 생긴다.

### NetworkPolicy — 일단 다 막고 필요한 것만 열기

이게 Zero Trust라는 개념인데, 생각보다 단순하다.

```yaml
# 들어오는 트래픽 전부 차단
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: default
spec:
  podSelector: {}
  policyTypes:
    - Ingress
```

`podSelector: {}`가 "모든 Pod한테 적용"이라는 뜻이다. 이렇게 하면 default 네임스페이스의 모든 Pod는 기본적으로 외부 트래픽을 받지 않는다.

나가는 트래픽도 마찬가지로 막아뒀고, DNS(포트 53)만 예외로 열어뒀다. DNS를 안 열면 서비스 이름으로 통신 자체가 안 되니까.

이렇게 하면 뭐가 좋냐면, 만약 Pod 하나가 뚫려도 다른 Pod로 옮겨가는 게(Lateral Movement) 차단된다. 실제로 보안 사고의 상당수가 이 횡방향 이동 때문에 피해가 커진다.

### RBAC — 누가 뭘 할 수 있는지 정하기

역할을 2개 만들었다:

- **developer**: Pod, Deployment, Service를 만들고 수정할 수 있음. 근데 삭제는 못함. Secret은 읽기만 가능
- **viewer**: 전부 읽기만 가능. 모니터링 용도

최소 권한 원칙(Principle of Least Privilege)이라고 하는데, 필요한 만큼만 권한을 주자는 거다. 실수로 운영 중인 리소스를 날리는 사고를 원천 차단할 수 있다.

### Pod Security Standards — 위험한 컨테이너 실행 차단

두 단계로 적용했다:

- **baseline** (강제): 특권 컨테이너, 호스트 네트워크 접근 같은 명백히 위험한 설정은 아예 차단
- **restricted** (경고): root 실행, 권한 상승 같은 건 일단 경고만 띄움

컨테이너가 root로 돌아가면 취약점 하나 터졌을 때 피해가 훨씬 크다. 이걸 시스템 레벨에서 막아두는 거다.

---

## 5. Dashboard 설치

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/dashboard/v2.7.0/aio/deploy/recommended.yaml
```

웹에서 클러스터 상태를 시각적으로 볼 수 있는 도구다. 토큰 기반 인증으로 접속하고, 관리자용 ServiceAccount를 따로 만들어서 사용한다.

근데 솔직히 말하면 k9s가 더 편하다. 터미널에서 `k9s` 치면 바로 실시간 모니터링이 되니까.

---

## 최종 구성도

```
┌──────────────────────────────────────────────────┐
│              Docker (macOS)                        │
│                                                    │
│  ┌──────────────────┐                             │
│  │ Control Plane     │  localhost:80  → HTTP       │
│  │  - API Server     │  localhost:443 → HTTPS      │
│  │  - etcd           │                             │
│  │  - Scheduler      │                             │
│  │  - Ingress Nginx  │                             │
│  └──────────────────┘                             │
│                                                    │
│  ┌──────────────┐  ┌──────────────┐               │
│  │ Worker 1      │  │ Worker 2      │              │
│  │  - App Pods   │  │  - App Pods   │              │
│  └──────────────┘  └──────────────┘               │
│                                                    │
│  보안:                                             │
│   NetworkPolicy (Zero Trust)                       │
│   RBAC (developer / viewer)                        │
│   Pod Security (baseline + restricted)             │
└──────────────────────────────────────────────────┘
```

---

## 삽질한 부분

- Docker Desktop이 꺼져있는 줄 모르고 `kind create cluster`를 실행해서 에러가 났다. Docker가 실행 중인지 먼저 확인하자.
- Dashboard Helm 차트 URL이 바뀌어서 설치가 안 됐다. 공식 문서를 확인하고 `kubectl apply`로 직접 설치했더니 해결됨.

## 이번에 배운 것

- Kind가 이렇게 가벼운 줄 몰랐다. 클러스터 만들고 부수는 데 부담이 없어서 실험하기 좋다.
- 보안은 나중에 하면 진짜 귀찮다. 처음에 세팅해두니까 이후에 앱 배포할 때 신경 쓸 게 줄어든다.
- Zero Trust가 거창한 게 아니라 "일단 막고 필요한 것만 열자"라는 단순한 원칙이었다.

## 다음에 할 것

- [ ] Python으로 간단한 앱 만들어서 K8s에 배포해보기
- [ ] Prometheus + Grafana로 모니터링 구축
- [ ] ArgoCD로 GitOps 도입
- [ ] GitHub Actions로 CI/CD 파이프라인 만들기
