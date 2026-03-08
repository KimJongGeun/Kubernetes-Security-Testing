# 로컬 K8s 환경 구축 정리

> 2026.03.08 구축 완료

## 환경

| 항목 | 버전 |
|---|---|
| OS | macOS (Apple M1 Pro) |
| Docker | 24.0.7 |
| kubectl | v1.28.2 |
| Kind | 0.31.0 |
| Helm | 4.1.1 |
| k9s | 0.50.18 |
| K8s | v1.35.0 |

## 클러스터 구성

```
┌──────────────────────────────────────────────────────┐
│              Docker (macOS)                            │
│                                                        │
│  ┌──────────────────┐                                 │
│  │ Control Plane     │  localhost:80  → HTTP           │
│  │  - API Server     │  localhost:443 → HTTPS          │
│  │  - etcd           │  localhost:30000-30001          │
│  │  - Scheduler      │    → NodePort                   │
│  │  - Controller Mgr │                                 │
│  │  - Ingress Nginx  │                                 │
│  └──────────────────┘                                 │
│                                                        │
│  ┌──────────────┐  ┌──────────────┐                   │
│  │ Worker 1      │  │ Worker 2      │                  │
│  │  - kubelet    │  │  - kubelet    │                  │
│  │  - kube-proxy │  │  - kube-proxy │                  │
│  │  - App Pods   │  │  - App Pods   │                  │
│  └──────────────┘  └──────────────┘                   │
└──────────────────────────────────────────────────────┘
```

노드 3개 모두 Ready 상태로 정상 동작 중.

## 설치된 컴포넌트

- **Nginx Ingress Controller** — 외부 트래픽을 내부 서비스로 라우팅
- **Kubernetes Dashboard** — 웹 UI로 클러스터 관리
- **CoreDNS** — 클러스터 내부 DNS 해석
- **kindnet** — CNI 네트워크 플러그인

## 보안 설정

### NetworkPolicy
기본적으로 default 네임스페이스의 모든 인바운드/아웃바운드 트래픽을 차단해뒀다. DNS만 예외로 허용.
앱을 배포할 때 필요한 통신만 별도로 열어주는 방식이다.

### RBAC
역할 2개를 만들었다:
- **developer** — 리소스 조회/생성/수정 가능, 삭제 불가, Secret은 읽기만
- **viewer** — 모든 리소스 읽기 전용

### Pod Security Standards
- baseline 레벨을 강제 적용해서 특권 컨테이너나 호스트 접근을 차단
- restricted 레벨은 경고 모드로 적용해서 로그만 남기는 중

## 자주 쓰는 명령어

```bash
# 노드 확인
kubectl get nodes

# 전체 Pod 확인
kubectl get pods -A

# Pod 상세 정보
kubectl describe pod <pod-name>

# 로그 보기
kubectl logs <pod-name>

# k9s 실행
k9s --context kind-local-k8s

# 대시보드 프록시
kubectl proxy

# 클러스터 삭제
kind delete cluster --name local-k8s

# 클러스터 재생성
kind create cluster --config k8s/kind-config.yaml
```

## 파일 구조

```
k8s/
├── kind-config.yaml           # 클러스터 설정 (3노드)
└── security/
    ├── network-policy.yaml    # 네트워크 정책
    ├── rbac.yaml              # 역할/권한
    ├── pod-security.yaml      # Pod 보안
    └── dashboard-admin.yaml   # 대시보드 계정
```

## 작업 이력

| 날짜 | 작업 |
|---|---|
| 2026.03.08 | Kind, Helm, k9s 설치 |
| 2026.03.08 | 멀티노드 클러스터 생성 (CP 1 + Worker 2) |
| 2026.03.08 | Nginx Ingress Controller 설치 |
| 2026.03.08 | NetworkPolicy, RBAC, Pod Security 적용 |
| 2026.03.08 | Kubernetes Dashboard 설치 |
| 2026.03.08 | 전체 검증 완료 |
| 2026.03.08 | ArgoCD 설치 및 GitOps 구축 |
| 2026.03.08 | 샘플 앱(nginx) ArgoCD 자동 배포 확인 |
