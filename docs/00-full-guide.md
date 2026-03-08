# 로컬 Kubernetes 환경 구축 - 완전 학습 가이드

> 이 문서는 Docker 위에 Kubernetes 클러스터를 구축하고 보안 설정까지 적용한 전체 과정을 담고 있다.
> Kubernetes를 처음 접하는 사람도 이해할 수 있도록 모든 개념과 명령어를 하나하나 설명한다.

---

# 목차

1. [사전 지식 — 이것만 알면 된다](#1-사전-지식--이것만-알면-된다)
2. [전체 구성도 — 우리가 만들 것](#2-전체-구성도--우리가-만들-것)
3. [도구 설치](#3-도구-설치)
4. [클러스터 생성 — kind-config.yaml 완전 해부](#4-클러스터-생성--kind-configyaml-완전-해부)
5. [Ingress Controller — 외부 트래픽 연결](#5-ingress-controller--외부-트래픽-연결)
6. [보안 1: NetworkPolicy — 네트워크 격리](#6-보안-1-networkpolicy--네트워크-격리)
7. [보안 2: RBAC — 권한 관리](#7-보안-2-rbac--권한-관리)
8. [보안 3: Pod Security — 컨테이너 실행 제한](#8-보안-3-pod-security--컨테이너-실행-제한)
9. [Dashboard — 웹 UI 모니터링](#9-dashboard--웹-ui-모니터링)
10. [k9s — 터미널 모니터링 도구](#10-k9s--터미널-모니터링-도구)
11. [ArgoCD — GitOps 자동 배포](#11-argocd--gitops-자동-배포)
12. [kubectl 명령어 정리](#12-kubectl-명령어-정리)
13. [파일 구조 총정리](#13-파일-구조-총정리)
14. [트러블슈팅](#14-트러블슈팅)
15. [클러스터 삭제 및 재생성](#15-클러스터-삭제-및-재생성)

---

# 1. 사전 지식 — 이것만 알면 된다

## Kubernetes(K8s)가 뭔가?

컨테이너(Docker)를 대규모로 관리하는 시스템이다.

Docker 하나로 앱을 돌리는 건 쉽다. 근데 컨테이너가 100개, 1000개가 되면?
어떤 서버에 띄울지, 죽으면 다시 살릴지, 트래픽 몰리면 늘릴지... 이걸 사람이 일일이 하면 미친다.
Kubernetes가 이걸 자동으로 해준다.

## 핵심 용어 정리

| 용어 | 비유 | 설명 |
|---|---|---|
| **Cluster** | 공장 전체 | 여러 서버(노드)를 묶은 하나의 환경 |
| **Node** | 공장의 각 건물 | 실제 서버 하나. 컨테이너가 여기서 돌아감 |
| **Control Plane** | 관제탑 | 클러스터 전체를 관리하는 노드. 명령을 받고 스케줄링 |
| **Worker Node** | 생산 라인 | 실제로 앱 컨테이너가 돌아가는 노드 |
| **Pod** | 작업자 1명 | 컨테이너를 감싸는 최소 단위. 보통 컨테이너 1개 = Pod 1개 |
| **Deployment** | 작업 지시서 | "이 Pod를 3개 유지해라" 같은 선언. Pod가 죽으면 자동 재생성 |
| **Service** | 안내 데스크 | Pod에 접근할 수 있는 고정 주소. Pod는 죽었다 살아나면 IP가 바뀌는데 Service는 안 바뀜 |
| **Ingress** | 정문 경비 | 외부 HTTP 요청을 어떤 Service로 보낼지 결정하는 규칙 |
| **Namespace** | 부서 | 리소스를 논리적으로 분리하는 공간. 개발/운영 환경 분리 등에 사용 |
| **ConfigMap** | 설정 파일 | 환경 변수 등 설정값을 Pod에 전달 |
| **Secret** | 금고 | 비밀번호, 토큰 등 민감한 데이터를 저장 |

## Kind가 뭔가?

**K**ubernetes **IN** **D**ocker의 약자다.

Docker 컨테이너를 Kubernetes 노드처럼 사용한다.
실제로 `docker ps`를 치면 K8s 노드가 Docker 컨테이너로 돌아가는 걸 볼 수 있다.

```bash
$ docker ps
CONTAINER ID   IMAGE                  NAMES
abc123         kindest/node:v1.35.0   local-k8s-control-plane
def456         kindest/node:v1.35.0   local-k8s-worker
ghi789         kindest/node:v1.35.0   local-k8s-worker2
```

클라우드 비용 없이 로컬에서 실제 K8s와 거의 동일한 환경을 만들 수 있다.

---

# 2. 전체 구성도 — 우리가 만들 것

```
내 Mac (호스트)
│
├── Docker Desktop (실행 중)
│   │
│   └── Kind 클러스터 "local-k8s"
│       │
│       ├── Control Plane (관제탑)
│       │   ├── API Server      ← 모든 명령이 여기로 들어옴
│       │   ├── etcd             ← 클러스터 상태 DB
│       │   ├── Scheduler        ← Pod를 어떤 Worker에 배치할지 결정
│       │   ├── Controller Mgr   ← Deployment 등의 상태를 유지
│       │   └── Ingress Nginx    ← 외부 HTTP 트래픽 라우팅
│       │
│       ├── Worker Node 1 (생산 라인 1)
│       │   └── 앱 Pod들이 여기서 실행됨
│       │
│       └── Worker Node 2 (생산 라인 2)
│           └── 앱 Pod들이 여기서 실행됨
│
├── 포트 매핑
│   ├── localhost:80   → 클러스터 HTTP
│   ├── localhost:443  → 클러스터 HTTPS
│   └── localhost:30000-30001 → NodePort
│
└── 보안 설정
    ├── NetworkPolicy  → 네트워크 트래픽 격리
    ├── RBAC           → 역할별 권한 제한
    └── Pod Security   → 위험한 컨테이너 차단
```

---

# 3. 도구 설치

## 설치 명령어

```bash
brew install kind kubectl helm k9s
```

## 각 도구가 하는 일

### kind — 클러스터 만드는 도구
```bash
kind create cluster    # 클러스터 생성
kind delete cluster    # 클러스터 삭제
kind get clusters      # 클러스터 목록 확인
```

### kubectl — 클러스터에 명령을 내리는 도구
K8s의 메인 CLI다. 거의 모든 작업이 kubectl로 이루어진다.
```bash
kubectl get pods          # Pod 목록
kubectl apply -f 파일.yaml  # 설정 적용
kubectl delete pod 이름    # Pod 삭제
```

### helm — K8s 패키지 매니저
복잡한 앱을 한 줄로 설치할 수 있게 해주는 도구다.
예를 들어 Prometheus를 직접 설치하면 YAML 파일이 10개 넘게 필요한데, Helm이면 한 줄이다.

### k9s — 터미널 모니터링 도구
`kubectl`로 일일이 치는 대신, 실시간으로 클러스터 상태를 보여주는 터미널 UI다.
10장에서 자세히 다룬다.

## 설치 확인

```bash
kind --version      # kind version 0.31.0
kubectl version --client   # Client Version: v1.28.2
helm version --short       # v4.1.1
k9s version                # Version: 0.50.18
```

---

# 4. 클러스터 생성 — kind-config.yaml 완전 해부

## 파일 위치: `k8s/kind-config.yaml`

```yaml
kind: Cluster                          # 이 파일이 Kind 클러스터 설정이라는 뜻
apiVersion: kind.x-k8s.io/v1alpha4     # Kind API 버전
name: local-k8s                        # 클러스터 이름 (나중에 삭제할 때 이 이름 사용)
nodes:
  # ── Control Plane ──
  - role: control-plane                # 이 노드는 관제탑 역할
    kubeadmConfigPatches:
      - |
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"
            # ↑ "이 노드에 Ingress Controller를 설치해도 된다"는 라벨
            #   Ingress Controller가 이 라벨이 있는 노드에만 배치됨

    extraPortMappings:
      # 호스트(내 Mac)의 포트를 클러스터 내부와 연결
      - containerPort: 80              # 클러스터 내부 80번 포트
        hostPort: 80                   # 내 Mac의 80번 포트
        protocol: TCP                  # → localhost:80으로 접근 가능
      - containerPort: 443
        hostPort: 443
        protocol: TCP                  # → localhost:443으로 접근 가능
      - containerPort: 30000
        hostPort: 30000
        protocol: TCP                  # → NodePort 서비스용
      - containerPort: 30001
        hostPort: 30001
        protocol: TCP

  # ── Worker 노드들 ──
  - role: worker                       # 앱이 실제로 돌아가는 노드 1
  - role: worker                       # 앱이 실제로 돌아가는 노드 2
```

### 왜 Worker를 2대 뒀나?

Worker가 1대면 Pod가 무조건 거기서 돌아간다. 분산이란 개념을 체험할 수가 없다.
2대를 두면 K8s Scheduler가 Pod를 어느 노드에 배치할지 결정하는 과정을 직접 볼 수 있다.

```bash
# Pod가 어떤 노드에 배치됐는지 확인
kubectl get pods -o wide
# NAME        READY   NODE
# nginx-abc   1/1     local-k8s-worker
# nginx-def   1/1     local-k8s-worker2   ← 다른 노드에 분산됨
```

### extraPortMappings가 없으면?

클러스터 안에서는 통신이 되지만, 내 Mac의 브라우저에서는 접근이 안 된다.
이 설정이 "내 Mac의 80번 포트 = 클러스터의 80번 포트"로 연결해주는 다리 역할을 한다.

## 클러스터 생성 명령어

```bash
kind create cluster --config k8s/kind-config.yaml
```

실행하면 이런 흐름으로 진행된다:

```
1. Docker 이미지(kindest/node) 다운로드
2. Docker 컨테이너 3개 생성 (CP + Worker 2)
3. kubeadm으로 K8s 초기화
4. CNI(네트워크 플러그인) 설치
5. Worker 노드를 클러스터에 합류시킴
6. kubectl 설정(~/.kube/config)을 자동으로 세팅
```

## 생성 확인

```bash
# 노드 상태 확인
kubectl get nodes
# NAME                      STATUS   ROLES           VERSION
# local-k8s-control-plane   Ready    control-plane   v1.35.0
# local-k8s-worker          Ready    <none>          v1.35.0
# local-k8s-worker2         Ready    <none>          v1.35.0

# Docker에서도 확인 가능 (K8s 노드 = Docker 컨테이너)
docker ps
```

3개 노드 모두 `Ready`면 성공이다.

---

# 5. Ingress Controller — 외부 트래픽 연결

## 개념

K8s 안에 앱을 배포해도 기본적으로 외부에서 접근이 안 된다.
Ingress Controller가 "외부 요청 → 내부 서비스" 라우팅을 담당한다.

```
브라우저에서 localhost:80 접속
    ↓
Ingress Controller (Nginx)가 요청을 받음
    ↓
Ingress 규칙에 따라 적절한 Service로 전달
    ↓
Service가 해당 Pod로 전달
    ↓
Pod가 응답 반환
```

비유하면 건물 1층 안내데스크 같은 거다.
"개발팀 찾아왔어요" → "3층 302호로 가세요" 이런 식으로 안내해주는 역할.

## 설치

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
```

이 명령어 하나로 다음이 자동 생성된다:
- `ingress-nginx` 네임스페이스
- Nginx Ingress Controller Pod
- 관련 Service, Role, ConfigMap 등

## 설치 확인

```bash
# Ingress Controller Pod가 Running인지 확인
kubectl get pods -n ingress-nginx

# 준비될 때까지 대기 (자동으로 기다려줌)
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s
```

## 나중에 사용하는 법 (예시)

앱을 배포한 뒤 Ingress 규칙을 만들면 된다:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-app-ingress
spec:
  rules:
    - http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: my-app-service
                port:
                  number: 80
```

이렇게 하면 `localhost:80` → `my-app-service` → 앱 Pod로 트래픽이 흐른다.

---

# 6. 보안 1: NetworkPolicy — 네트워크 격리

## 파일 위치: `k8s/security/network-policy.yaml`

## 왜 필요한가?

K8s에서는 기본적으로 모든 Pod가 서로 통신할 수 있다.
이게 편하긴 한데, 보안상 위험하다.

만약 Pod A가 해킹당했다고 치자. NetworkPolicy가 없으면:
```
해커 → Pod A (뚫림) → Pod B (자유 접근) → Pod C (자유 접근) → DB Pod (데이터 탈취)
```

NetworkPolicy가 있으면:
```
해커 → Pod A (뚫림) → Pod B (차단!) ← 여기서 막힘
```

이걸 **Lateral Movement(횡방향 이동) 차단**이라고 한다.

## 파일 분석

이 파일에는 3개의 정책이 들어있다. 하나씩 보자.

### 정책 1: 들어오는 트래픽 전부 차단

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress      # 정책 이름
  namespace: default               # default 네임스페이스에만 적용
spec:
  podSelector: {}                  # {} = 모든 Pod에 적용
  policyTypes:
    - Ingress                      # Ingress = 들어오는 트래픽
```

`podSelector: {}` 가 핵심이다. 빈 객체 `{}`는 "조건 없이 전부"라는 뜻이다.
결과: default 네임스페이스의 모든 Pod로 들어오는 트래픽이 차단된다.

### 정책 2: 나가는 트래픽 전부 차단

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-egress
  namespace: default
spec:
  podSelector: {}
  policyTypes:
    - Egress                       # Egress = 나가는 트래픽
```

들어오는 것뿐만 아니라 나가는 것도 막는다.
이러면 Pod에서 외부 API를 호출하거나 다른 Pod에 접근하는 것도 차단된다.

### 정책 3: DNS만 허용

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns
  namespace: default
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress:
    - to: []                       # 목적지 제한 없음
      ports:
        - protocol: UDP
          port: 53                 # DNS는 UDP 53번 포트
        - protocol: TCP
          port: 53                 # DNS TCP fallback
```

전부 막으면 DNS도 안 된다. DNS가 안 되면 `my-service`같은 서비스 이름을 IP로 변환할 수 없어서 아무것도 못 한다. 그래서 DNS(포트 53)만 예외로 열어둔다.

## 적용 명령어

```bash
kubectl apply -f k8s/security/network-policy.yaml
```

## 확인

```bash
# 적용된 정책 확인
kubectl get networkpolicy -n default
# NAME                   POD-SELECTOR   AGE
# default-deny-ingress   <none>         ...
# default-deny-egress    <none>         ...
# allow-dns              <none>         ...
```

## 나중에 특정 통신을 허용하려면?

예를 들어 frontend Pod가 backend Pod에 접근해야 한다면:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend-to-backend
  namespace: default
spec:
  podSelector:
    matchLabels:
      app: backend                 # backend Pod에 적용
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: frontend        # frontend에서 오는 트래픽만 허용
      ports:
        - protocol: TCP
          port: 8080
```

이런 식으로 필요한 통신만 하나씩 열어주면 된다.

---

# 7. 보안 2: RBAC — 권한 관리

## 파일 위치: `k8s/security/rbac.yaml`

## RBAC이 뭔가?

**R**ole **B**ased **A**ccess **C**ontrol의 약자다. 역할 기반 접근 제어.

쉽게 말하면 "이 사람은 뭘 할 수 있고, 뭘 못 하는지" 정하는 것이다.

회사로 비유하면:
- 인턴: 문서 읽기만 가능
- 개발자: 코드 읽기/쓰기 가능, 서버 삭제는 불가
- 관리자: 전부 가능

K8s에서도 똑같다.

## RBAC의 구조

```
Role (역할)          → "무엇을" 할 수 있는지 정의
ServiceAccount (계정) → "누가"에 해당
RoleBinding (연결)   → Role과 ServiceAccount를 연결
```

## 파일 분석

### developer 역할

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: developer
  namespace: default
rules:
  # 규칙 1: Pod, Deployment, Service, ConfigMap에 대한 권한
  - apiGroups: ["", "apps"]
    resources: ["pods", "deployments", "services", "configmaps"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
    #        ↑읽기   ↑목록   ↑감시   ↑생성    ↑수정    ↑부분수정
    # "delete"가 없다 → 삭제 불가!

  # 규칙 2: Pod 로그 읽기
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["get", "list"]

  # 규칙 3: Secret은 읽기만
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get", "list"]
    # create, update가 없다 → Secret 생성/수정 불가!
```

핵심은 `verbs`(동사) 부분이다.
`delete`가 없으면 삭제를 못 한다. 이게 RBAC의 전부다.

### viewer 역할

```yaml
kind: Role
metadata:
  name: viewer
rules:
  - apiGroups: ["", "apps", "networking.k8s.io"]
    resources: ["*"]                    # 모든 리소스
    verbs: ["get", "list", "watch"]     # 읽기만 가능
```

모든 리소스를 볼 수 있지만, 수정/생성/삭제는 전부 불가.
모니터링 담당자한테 딱 맞는 권한이다.

### ServiceAccount (계정)

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: developer-sa          # 개발자용 계정
  namespace: default
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: viewer-sa             # 뷰어용 계정
  namespace: default
```

사람이 아니라 "서비스 어카운트"라는 가상 계정을 만든다.
실제로 Pod를 배포할 때 이 계정을 지정하면 해당 권한으로 동작한다.

### RoleBinding (역할 연결)

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: developer-binding
subjects:
  - kind: ServiceAccount
    name: developer-sa         # 이 계정에게
roleRef:
  kind: Role
  name: developer              # 이 역할을 부여한다
```

## 적용 및 확인

```bash
# 적용
kubectl apply -f k8s/security/rbac.yaml

# 확인
kubectl get roles -n default
kubectl get rolebindings -n default
kubectl get sa -n default
```

## 권한 테스트 방법

```bash
# developer-sa가 Pod를 만들 수 있는지 확인
kubectl auth can-i create pods --as=system:serviceaccount:default:developer-sa
# yes

# developer-sa가 Pod를 삭제할 수 있는지 확인
kubectl auth can-i delete pods --as=system:serviceaccount:default:developer-sa
# no

# viewer-sa가 Pod를 만들 수 있는지 확인
kubectl auth can-i create pods --as=system:serviceaccount:default:viewer-sa
# no
```

---

# 8. 보안 3: Pod Security — 컨테이너 실행 제한

## 파일 위치: `k8s/security/pod-security.yaml`

## 왜 필요한가?

Docker 컨테이너는 기본적으로 root로 실행된다.
root 권한이 있는 컨테이너가 해킹당하면 호스트 OS까지 위험해질 수 있다.

Pod Security Standards는 "이런 위험한 설정으로는 Pod를 못 만들게" 차단하는 거다.

## 3가지 보안 레벨

| 레벨 | 엄격도 | 차단하는 것 |
|---|---|---|
| **privileged** | 제한 없음 | 아무것도 안 막음 (기본값) |
| **baseline** | 기본 보안 | 호스트 네트워크, 특권 컨테이너, hostPath 등 |
| **restricted** | 엄격 보안 | baseline + root 실행, 권한 상승 등 |

## 파일 분석

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: default
  labels:
    # enforce → 위반하면 Pod 생성 자체를 차단
    pod-security.kubernetes.io/enforce: baseline

    # warn → 위반하면 경고 메시지를 보여줌 (생성은 됨)
    pod-security.kubernetes.io/warn: restricted

    # audit → 위반하면 감사 로그에 기록 (생성은 됨)
    pod-security.kubernetes.io/audit: restricted
```

3개의 라벨이 각각 다른 동작을 한다:

- **enforce: baseline** → baseline 위반 시 Pod 생성 자체가 거부됨
- **warn: restricted** → restricted 위반 시 터미널에 경고 메시지 표시
- **audit: restricted** → restricted 위반 시 감사 로그에 기록

왜 이렇게 2단계로 나눴냐면, restricted를 바로 enforce하면 기존 앱이 다 깨질 수 있어서다.
일단 경고만 띄우면서 어떤 앱이 위반하는지 파악한 뒤, 나중에 enforce로 올리면 된다.

## baseline이 차단하는 것들

| 차단 항목 | 이유 |
|---|---|
| `privileged: true` | 컨테이너에 호스트의 모든 권한을 줌. 사실상 root |
| `hostNetwork: true` | 컨테이너가 호스트의 네트워크를 직접 사용 |
| `hostPID: true` | 호스트의 프로세스 목록에 접근 가능 |
| `hostIPC: true` | 호스트의 프로세스 간 통신에 접근 가능 |

## 적용 및 확인

```bash
# 적용
kubectl apply -f k8s/security/pod-security.yaml

# 라벨 확인
kubectl get ns default --show-labels
# pod-security.kubernetes.io/enforce=baseline,
# pod-security.kubernetes.io/warn=restricted,
# pod-security.kubernetes.io/audit=restricted
```

## 테스트: 특권 컨테이너 만들기 시도

```bash
# 특권 컨테이너 생성 시도 → 거부되어야 정상
kubectl run bad-pod --image=nginx --overrides='{
  "spec": {
    "containers": [{
      "name": "bad",
      "image": "nginx",
      "securityContext": {"privileged": true}
    }]
  }
}'
# Error: admission webhook denied the request:
# pod violates PodSecurity "baseline:latest"
```

---

# 9. Dashboard — 웹 UI 모니터링

## 파일 위치: `k8s/security/dashboard-admin.yaml`

## 설치

```bash
# Dashboard 본체 설치
kubectl apply -f https://raw.githubusercontent.com/kubernetes/dashboard/v2.7.0/aio/deploy/recommended.yaml

# 관리자 계정 생성 (우리가 만든 파일)
kubectl apply -f k8s/security/dashboard-admin.yaml
```

## dashboard-admin.yaml 분석

```yaml
# 1. 서비스 어카운트 생성
apiVersion: v1
kind: ServiceAccount
metadata:
  name: dashboard-admin
  namespace: kubernetes-dashboard     # Dashboard 전용 네임스페이스

---
# 2. 클러스터 관리자 권한 바인딩
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding              # ClusterRoleBinding = 전체 클러스터 범위
metadata:
  name: dashboard-admin-binding
subjects:
  - kind: ServiceAccount
    name: dashboard-admin
    namespace: kubernetes-dashboard
roleRef:
  kind: ClusterRole
  name: cluster-admin                 # K8s 기본 제공 최고 권한
  apiGroup: rbac.authorization.k8s.io

---
# 3. 토큰 시크릿 생성
apiVersion: v1
kind: Secret
metadata:
  name: dashboard-admin-token
  namespace: kubernetes-dashboard
  annotations:
    kubernetes.io/service-account.name: dashboard-admin  # 이 계정의 토큰
type: kubernetes.io/service-account-token
# 실제 토큰 값은 K8s가 자동 생성한다. 이 파일에는 없다.
```

## 접속 방법

```bash
# 1단계: 프록시 시작 (터미널 하나 열어두기)
kubectl proxy

# 2단계: 브라우저에서 이 URL 접속
# http://localhost:8001/api/v1/namespaces/kubernetes-dashboard/services/https:kubernetes-dashboard:/proxy/

# 3단계: 토큰 복사 (Mac 클립보드에 자동 복사)
kubectl get secret dashboard-admin-token -n kubernetes-dashboard \
  -o jsonpath='{.data.token}' | base64 -d | pbcopy

# 4단계: Dashboard 로그인 화면에서 Token 선택 → Cmd+V 붙여넣기 → Sign in
```

## Dashboard에서 할 수 있는 것

- 네임스페이스별 Pod, Deployment, Service 목록 보기
- Pod 로그 확인
- YAML 편집
- 리소스 생성/삭제
- 클러스터 이벤트 확인

---

# 10. k9s — 터미널 모니터링 도구

## 실행

```bash
k9s --context kind-local-k8s
```

## 화면 구조

```
┌─ k9s ─────────────────────────────────────────────┐
│ Context: kind-local-k8s   Cluster: kind-local-k8s │  ← 현재 클러스터
│                                                     │
│ Pods(default)  [5 items]                            │  ← 현재 보고 있는 리소스
│                                                     │
│ NAME              READY  STATUS   RESTARTS  NODE    │
│ nginx-abc123      1/1    Running  0         worker  │  ← 초록=정상
│ nginx-def456      1/1    Running  0         worker2 │
│ bad-pod-xyz       0/1    Error    3         worker  │  ← 빨강=문제
│                                                     │
│ <pod> | <q>:Quit <?>:Help </:Filter                 │  ← 단축키 안내
└─────────────────────────────────────────────────────┘
```

## 핵심 단축키

### 화면 이동
| 키 | 동작 | 예시 |
|---|---|---|
| `:` | 리소스 타입 이동 | `:pods` `:deploy` `:svc` `:ns` `:events` |
| `0` | 모든 네임스페이스 보기 | 전체 클러스터의 Pod를 한번에 |
| `Esc` | 뒤로 가기 | |
| `q` | 종료 | |

### Pod 조작
| 키 | 동작 | 설명 |
|---|---|---|
| `Enter` | 상세 보기 | 선택한 Pod 안의 컨테이너 목록 |
| `l` | 로그 보기 | 실시간 로그 스트리밍 |
| `s` | 셸 접속 | Pod 안에 bash/sh로 접속 |
| `d` | describe | kubectl describe와 동일 |
| `y` | YAML 보기 | 전체 YAML 확인 |
| `Ctrl+d` | 삭제 | 리소스 삭제 (확인 창 뜸) |

### 검색/필터
| 키 | 동작 | 예시 |
|---|---|---|
| `/` | 이름 필터 | `/nginx` → nginx가 포함된 것만 |
| `?` | 도움말 | 전체 단축키 목록 |

## 자주 쓰는 화면들

```bash
# Pod 목록 (기본)
:pods

# Deployment 목록
:deploy

# Service 목록
:svc

# 네임스페이스 목록
:ns

# NetworkPolicy 목록
:networkpolicy  또는  :netpol

# 이벤트 (에러 추적에 유용)
:events

# 노드 상태
:nodes

# Secret 목록
:secrets

# ConfigMap 목록
:configmaps  또는  :cm
```

## 색상 의미

- **초록**: 정상 (Running, Ready)
- **빨강**: 문제 있음 (Error, CrashLoopBackOff)
- **노랑**: 진행 중 (Pending, ContainerCreating)

---

# 11. ArgoCD — GitOps 자동 배포

## GitOps란?

Git에 있는 YAML = 클러스터의 실제 상태. 이게 전부다.

Git에 push하면 ArgoCD가 자동으로 클러스터에 반영한다. 사람이 kubectl apply를 칠 필요가 없다.

```
git push → ArgoCD 감지 (3분 주기) → 자동 kubectl apply → 배포 완료
```

## 설치

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

## 웹 UI 접속

```bash
# 포트포워딩
kubectl port-forward svc/argocd-server -n argocd 8080:443

# 브라우저: https://localhost:8080
# ID: admin
# PW 확인:
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d
```

## Application 등록

ArgoCD한테 "이 Git 레포의 이 폴더를 감시해라"고 알려주는 설정이다.

```yaml
# argocd/sample-nginx-app.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: sample-nginx
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/KimJongGeun/Kubernetes-Security-Testing.git
    targetRevision: main
    path: apps/sample-nginx       # 이 폴더를 감시
  destination:
    server: https://kubernetes.default.svc
    namespace: default
  syncPolicy:
    automated:
      selfHeal: true              # kubectl로 직접 바꿔도 Git 상태로 되돌림
      prune: true                 # Git에서 삭제하면 클러스터에서도 삭제
```

적용:
```bash
kubectl apply -f argocd/sample-nginx-app.yaml
```

## 핵심 개념

| 개념 | 설명 |
|---|---|
| **Sync** | Git과 클러스터 상태를 일치시키는 동작 |
| **Self-Heal** | 누가 직접 바꿔도 Git 기준으로 원복 |
| **Prune** | Git에서 파일 삭제 시 클러스터 리소스도 삭제 |
| **Synced** | Git = 클러스터 (일치) |
| **OutOfSync** | Git ≠ 클러스터 (불일치, sync 필요) |
| **Healthy** | 배포된 리소스가 정상 동작 중 |

## 자동 배포 테스트

YAML 수정 후 git push하면 ArgoCD가 자동 반영한다:
```bash
# replicas: 2 → 3으로 수정
# git commit & push
# → 3분 내에 Pod가 3개로 늘어남
```

> 상세 가이드: [docs/02-argocd-gitops.md](02-argocd-gitops.md)

---

# 12. kubectl 명령어 정리

## 기본 조회

```bash
# 노드 상태
kubectl get nodes

# 전체 네임스페이스의 모든 Pod
kubectl get pods -A

# 특정 네임스페이스의 Pod
kubectl get pods -n kube-system

# Pod가 어떤 노드에 있는지 상세 보기
kubectl get pods -o wide

# 모든 리소스 한번에 보기
kubectl get all

# YAML 형태로 보기
kubectl get pod <이름> -o yaml
```

## 상세 정보

```bash
# Pod 상세 정보 (이벤트, 에러 원인 확인)
kubectl describe pod <이름>

# 노드 상세 정보
kubectl describe node <이름>
```

## 로그

```bash
# Pod 로그
kubectl logs <pod-이름>

# 실시간 로그 (tail -f처럼)
kubectl logs <pod-이름> -f

# 이전 컨테이너 로그 (재시작된 경우)
kubectl logs <pod-이름> --previous
```

## 리소스 생성/적용

```bash
# YAML 파일로 리소스 생성
kubectl apply -f 파일.yaml

# 폴더 안의 모든 YAML 적용
kubectl apply -f k8s/security/

# 간단한 Pod 생성 (테스트용)
kubectl run test-nginx --image=nginx

# Deployment 생성
kubectl create deployment my-app --image=nginx --replicas=3
```

## 삭제

```bash
# Pod 삭제
kubectl delete pod <이름>

# YAML 기반으로 삭제
kubectl delete -f 파일.yaml

# 네임스페이스의 모든 Pod 삭제
kubectl delete pods --all -n default
```

## 디버깅

```bash
# Pod 안에 셸 접속
kubectl exec -it <pod-이름> -- /bin/bash

# Pod 안에서 명령어 실행
kubectl exec <pod-이름> -- ls /app

# 이벤트 확인 (최근 순서)
kubectl get events --sort-by='.lastTimestamp'

# 리소스 사용량 확인
kubectl top nodes
kubectl top pods
```

## 컨텍스트

```bash
# 현재 컨텍스트 확인
kubectl config current-context

# 컨텍스트 목록
kubectl config get-contexts

# 컨텍스트 변경
kubectl config use-context kind-local-k8s
```

---

# 13. 파일 구조 총정리

```
Jay_code/
│
├── .gitignore                          # Git에서 제외할 파일 목록
│                                        # .venv, .env, .claude, *.key 등 제외
│
├── .vscode/                            # VS Code 설정
│   ├── settings.json                   # Python 인터프리터, 포맷터 설정
│   ├── extensions.json                 # 추천 확장 프로그램 목록
│   └── launch.json                     # F5 디버깅 설정
│
├── README.md                           # 프로젝트 소개 (GitHub 메인 페이지)
│
├── docs/                               # 학습 문서
│   ├── 00-full-guide.md                # 이 문서 (전체 가이드)
│   ├── 01-k8s-local-setup.md           # K8s 구축 과정
│   └── 02-argocd-gitops.md             # ArgoCD GitOps 구축 과정
│
├── argocd/                             # ArgoCD 설정
│   └── sample-nginx-app.yaml           # Application 등록 (GitHub 감시 설정)
│
├── apps/                               # ArgoCD가 배포하는 앱들
│   └── sample-nginx/
│       ├── deployment.yaml             # nginx Pod 2개 배포
│       ├── service.yaml                # ClusterIP Service
│       └── network-policy.yaml         # Ingress에서만 접근 허용
│
├── k8s-setup-plan.md                   # 구축 결과 요약
│
├── k8s/                                # Kubernetes 설정 파일들
│   ├── kind-config.yaml                # Kind 클러스터 설정
│   │                                    # - Control Plane 1대
│   │                                    # - Worker 2대
│   │                                    # - 포트 매핑 (80, 443, 30000-30001)
│   │
│   └── security/                       # 보안 설정
│       ├── network-policy.yaml         # 네트워크 정책
│       │                                # - 인바운드 전체 차단
│       │                                # - 아웃바운드 전체 차단
│       │                                # - DNS만 허용
│       │
│       ├── rbac.yaml                   # 역할 기반 접근 제어
│       │                                # - developer: 생성/수정 O, 삭제 X
│       │                                # - viewer: 읽기만 가능
│       │
│       ├── pod-security.yaml           # Pod 보안 표준
│       │                                # - baseline: 강제 적용
│       │                                # - restricted: 경고 모드
│       │
│       └── dashboard-admin.yaml        # Dashboard 관리자 계정
│                                        # - ServiceAccount 생성
│                                        # - cluster-admin 권한 바인딩
│                                        # - 토큰 시크릿 생성
│
└── python/                             # Python 프로젝트 (개발 예정)
    └── .venv/                          # 가상환경 (.gitignore로 제외됨)
```

---

# 14. Falco 런타임 보안

## Falco가 하는 일

eBPF로 커널 레벨에서 syscall을 감시해서, 컨테이너 안에서 일어나는 이상 행위를 실시간으로 탐지한다.

```
컨테이너에서 셸 실행 → openat() syscall → Falco eBPF 프로브가 캐치 → 룰 매칭 → 경고
```

## ArgoCD로 배포

```bash
kubectl apply -f argocd/falco-app.yaml
```

Falco 공식 Helm 차트를 ArgoCD가 직접 받아서 설치한다. GitHub push 없이도 ArgoCD가 Helm 레포에서 차트를 받아옴.

## 주요 설정

- `driver.kind: modern_ebpf` — Kind(Docker) 환경 호환
- `falcosidekick` — 이벤트를 웹 UI, Slack 등으로 전달
- `customRules` — 환경에 맞는 커스텀 탐지 룰

## 커스텀 룰 5가지

| 룰 | 심각도 | 탐지 내용 |
|---|---|---|
| Shell spawned in container | WARNING | 컨테이너에서 셸 실행 |
| Package manager in container | WARNING | apt, apk 등 패키지 설치 시도 |
| Network tool in container | WARNING | curl, wget, nc 실행 |
| Sensitive file modification | CRITICAL | /etc/passwd, /etc/shadow 수정 시도 |
| Reverse shell in container | CRITICAL | 리버스 셸 연결 시도 |

## Falcosidekick UI 접속

```bash
kubectl port-forward svc/falco-falcosidekick-ui -n falco 2802:2802
# http://localhost:2802
```

상세 내용: [Falco 런타임 보안 구축](03-falco-runtime-security.md)

---

# 15. 트러블슈팅

## "Docker daemon not running" 에러

```bash
# 에러 메시지
Cannot connect to the Docker daemon. Is the docker daemon running?

# 해결: Docker Desktop을 실행한다
open -a Docker
# 또는 Spotlight(Cmd+Space)에서 Docker 검색 후 실행

# Docker가 준비될 때까지 대기
while ! docker info > /dev/null 2>&1; do sleep 1; done
echo "Docker is ready"
```

## Pod가 Pending 상태에서 안 바뀜

```bash
# 원인 확인
kubectl describe pod <pod-이름>
# Events 섹션을 보면 원인이 나옴

# 흔한 원인:
# - 리소스 부족 (CPU/메모리)
# - 이미지 pull 실패
# - PVC 바인딩 대기
```

## Pod가 CrashLoopBackOff 상태

```bash
# 로그 확인
kubectl logs <pod-이름>

# 이전 컨테이너 로그 (재시작 전)
kubectl logs <pod-이름> --previous

# 흔한 원인:
# - 앱 에러로 프로세스가 종료됨
# - 환경 변수 누락
# - 설정 파일 경로 오류
```

## NetworkPolicy 때문에 통신이 안 됨

```bash
# 현재 적용된 정책 확인
kubectl get networkpolicy -n default

# 특정 정책 상세 보기
kubectl describe networkpolicy default-deny-ingress -n default

# 임시로 정책 삭제해서 테스트 (원인 파악 후 다시 적용)
kubectl delete networkpolicy default-deny-ingress -n default
```

## kubectl 명령어가 다른 클러스터를 가리킴

```bash
# 현재 컨텍스트 확인
kubectl config current-context

# Kind 클러스터로 변경
kubectl config use-context kind-local-k8s
```

---

# 16. 클러스터 삭제 및 재생성

## 클러스터만 삭제

```bash
kind delete cluster --name local-k8s
```

Docker 컨테이너 3개가 삭제되고, 모든 K8s 리소스가 사라진다.
설치한 도구(kind, kubectl, helm, k9s)는 그대로 남는다.

## 처음부터 다시 만들기

```bash
# 1. 클러스터 생성
kind create cluster --config k8s/kind-config.yaml

# 2. Ingress Controller 설치
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml

# 3. 보안 정책 전체 적용
kubectl apply -f k8s/security/

# 4. Dashboard 설치
kubectl apply -f https://raw.githubusercontent.com/kubernetes/dashboard/v2.7.0/aio/deploy/recommended.yaml

# 5. 확인
kubectl get nodes
kubectl get pods -A
```

5개 명령어면 전체 환경이 복원된다.

ArgoCD까지 포함하면:
```bash
# 6. ArgoCD 설치
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# 7. ArgoCD Application 등록
kubectl apply -f argocd/sample-nginx-app.yaml

# 8. Falco 런타임 보안 (ArgoCD로 배포)
kubectl apply -f argocd/falco-app.yaml
```

## 도구까지 전부 제거

```bash
# 클러스터 삭제
kind delete cluster --name local-k8s

# 도구 제거
brew uninstall kind helm k9s

# kubectl은 다른 용도로 쓸 수 있으니 남겨둬도 됨
```
