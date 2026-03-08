# ArgoCD로 GitOps 자동 배포 구축하기

> 2026.03.08

## GitOps가 뭔가

한 줄로 말하면 "Git이 곧 배포의 기준"이라는 개념이다.

기존 방식은 이렇다:
```
코드 수정 → git push → 서버에 SSH 접속 → kubectl apply 직접 실행
```

GitOps는 이렇다:
```
코드 수정 → git push → 끝. ArgoCD가 알아서 배포함
```

Git에 있는 YAML = 클러스터의 실제 상태. 이 둘이 다르면 ArgoCD가 자동으로 맞춰준다.

누가 실수로 kubectl로 직접 뭔가 바꿔도, ArgoCD가 "Git이랑 다르네?" 하고 원래대로 되돌린다. 이걸 Self-Heal이라고 한다.

---

## 왜 ArgoCD를 골랐나

GitOps 도구로 유명한 게 ArgoCD랑 Flux 두 가지다.

| | ArgoCD | Flux |
|---|---|---|
| UI | 웹 대시보드 있음 | 없음 (CLI만) |
| 학습 곡선 | 낮음 | 중간 |
| 시각화 | 앱 상태를 그래프로 보여줌 | 터미널에서 확인 |
| 커뮤니티 | CNCF Graduated, 가장 큼 | CNCF Graduated |

웹 UI에서 배포 상태를 시각적으로 볼 수 있다는 게 결정적이었다. 처음 배울 때는 눈에 보이는 게 중요하다.

---

## 전체 흐름

```
[GitHub 레포]
  apps/sample-nginx/
    ├── deployment.yaml
    ├── service.yaml
    └── network-policy.yaml
        │
        │ ArgoCD가 3분마다 확인
        ↓
[ArgoCD (K8s 클러스터 안에 설치됨)]
  "Git이랑 클러스터 상태 비교"
        │
        │ 다르면 자동 sync
        ↓
[K8s 클러스터]
  Pod, Service, NetworkPolicy 생성/수정/삭제
```

---

## Step 1: ArgoCD 설치

```bash
# argocd 네임스페이스 생성 + 설치
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

이 명령어 하나로 ArgoCD 서버, 컨트롤러, Redis, Repo Server 등이 전부 설치된다.

설치 확인:
```bash
kubectl get pods -n argocd
# NAME                                                READY   STATUS
# argocd-server-xxx                                   1/1     Running
# argocd-application-controller-0                     1/1     Running
# argocd-repo-server-xxx                              1/1     Running
# argocd-redis-xxx                                    1/1     Running
# argocd-dex-server-xxx                               1/1     Running
# argocd-notifications-controller-xxx                 1/1     Running
# argocd-applicationset-controller-xxx                1/1     Running
```

7개 Pod가 모두 Running이면 성공이다.

### 각 컴포넌트가 하는 일

| 컴포넌트 | 역할 |
|---|---|
| argocd-server | 웹 UI + API 서버 |
| argocd-application-controller | Git과 클러스터 상태 비교, sync 실행 |
| argocd-repo-server | Git 레포에서 YAML을 가져오는 역할 |
| argocd-redis | 캐시 (성능 최적화) |
| argocd-dex-server | SSO 인증 (GitHub 로그인 등) |
| argocd-notifications-controller | Slack 등으로 알림 전송 |

---

## Step 2: ArgoCD 웹 UI 접속

```bash
# 포트포워딩 (터미널 하나 열어두기)
kubectl port-forward svc/argocd-server -n argocd 8080:443

# 브라우저에서 접속
# https://localhost:8080
# "연결이 안전하지 않음" 경고 → 고급 → 계속 진행 (로컬 자체서명 인증서)
```

### 로그인 정보

```bash
# 초기 비밀번호 확인
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d
```

- ID: `admin`
- PW: 위 명령어로 나온 값

---

## Step 3: 샘플 앱 작성

ArgoCD가 감시할 YAML 파일들을 만들었다. `apps/sample-nginx/` 폴더에 3개 파일이 있다.

### deployment.yaml — Pod 2개 배포

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sample-nginx
  labels:
    app: sample-nginx
spec:
  replicas: 2                    # Pod 2개 유지
  selector:
    matchLabels:
      app: sample-nginx
  template:
    metadata:
      labels:
        app: sample-nginx
    spec:
      containers:
        - name: nginx
          image: nginx:1.27-alpine
          ports:
            - containerPort: 80
          resources:
            limits:              # 리소스 제한 (필수 습관)
              memory: "128Mi"
              cpu: "250m"
            requests:
              memory: "64Mi"
              cpu: "125m"
```

`resources`를 설정한 이유: 제한 없으면 Pod 하나가 노드의 리소스를 다 먹어버릴 수 있다. 운영 환경에서는 반드시 설정해야 한다.

### service.yaml — Pod에 접근할 고정 주소

```yaml
apiVersion: v1
kind: Service
metadata:
  name: sample-nginx
spec:
  selector:
    app: sample-nginx           # app=sample-nginx 라벨이 붙은 Pod에 연결
  ports:
    - protocol: TCP
      port: 80
      targetPort: 80
  type: ClusterIP               # 클러스터 내부에서만 접근 가능
```

Pod는 죽었다 살아나면 IP가 바뀐다. Service는 안 바뀌는 고정 주소를 제공한다.

### network-policy.yaml — 보안 통신 규칙

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-ingress-to-nginx
spec:
  podSelector:
    matchLabels:
      app: sample-nginx          # sample-nginx Pod에 적용
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ingress-nginx
                                 # ingress-nginx 네임스페이스에서 오는 트래픽만 허용
      ports:
        - protocol: TCP
          port: 80
```

기본 NetworkPolicy에서 모든 트래픽을 막아뒀으니, 이 앱에 필요한 트래픽만 명시적으로 열어주는 거다. Ingress Controller에서 오는 80번 포트 트래픽만 허용한다.

---

## Step 4: ArgoCD Application 등록

ArgoCD한테 "이 GitHub 레포의 이 폴더를 감시해라"고 알려주는 설정이다.

### argocd/sample-nginx-app.yaml

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: sample-nginx
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/KimJongGeun/Kubernetes-Security-Testing.git
    targetRevision: main         # main 브랜치를 감시
    path: apps/sample-nginx      # 이 폴더의 YAML을 배포
  destination:
    server: https://kubernetes.default.svc   # 현재 클러스터
    namespace: default
  syncPolicy:
    automated:
      selfHeal: true             # 클러스터 상태가 Git과 다르면 되돌림
      prune: true                # Git에서 삭제된 리소스는 클러스터에서도 삭제
    syncOptions:
      - CreateNamespace=true
```

핵심 설정 2가지:

- **selfHeal: true** — 누가 kubectl로 직접 바꿔도 ArgoCD가 Git 상태로 되돌린다
- **prune: true** — Git에서 YAML 파일을 삭제하면 클러스터의 해당 리소스도 삭제한다

### 적용

```bash
kubectl apply -f argocd/sample-nginx-app.yaml
```

### 확인

```bash
kubectl get application -n argocd
# NAME           SYNC STATUS   HEALTH STATUS
# sample-nginx   Synced        Healthy
```

`Synced` = Git과 클러스터가 일치, `Healthy` = Pod가 정상 작동 중.

ArgoCD 웹 UI에서도 sample-nginx 앱이 초록색으로 보인다.

---

## 자동 배포 테스트해보기

직접 해보면 이해가 빠르다.

### 테스트 1: replicas 변경

`apps/sample-nginx/deployment.yaml`에서:
```yaml
replicas: 2    →    replicas: 3
```

으로 바꾸고 git push하면:

```bash
git add . && git commit -m "scale: nginx replicas 2 → 3" && git push
```

ArgoCD가 자동으로 감지해서 Pod를 3개로 늘린다. (최대 3분 소요)

```bash
kubectl get pods -l app=sample-nginx
# 2개 → 3개로 변경됨
```

### 테스트 2: Self-Heal 확인

kubectl로 직접 Pod를 삭제해보자:
```bash
kubectl delete pod -l app=sample-nginx
```

ArgoCD가 "Git에는 replicas: 3인데 Pod가 없네?" 하고 자동으로 다시 만든다.

---

## ArgoCD 웹 UI 활용

### 앱 상태 확인
- 초록색 하트 = Healthy (정상)
- 노란색 = Progressing (진행 중)
- 빨간색 = Degraded (문제 있음)

### 수동 Sync
자동 sync를 기다리기 싫으면 UI에서 SYNC 버튼을 누르면 즉시 반영된다.

### Diff 확인
DIFF 버튼을 누르면 Git과 클러스터의 차이점을 볼 수 있다.

### 리소스 트리
앱을 클릭하면 Deployment → ReplicaSet → Pod 관계를 트리 형태로 보여준다.
어떤 Pod가 어떤 노드에 있는지도 확인 가능하다.

---

## 배운 것

- GitOps는 "Git = 배포의 진실 소스(Single Source of Truth)"라는 단순한 원칙이다
- ArgoCD의 selfHeal이 강력하다. 실수로 뭔가 건드려도 Git 상태로 알아서 돌아간다
- 배포 이력이 Git commit에 다 남으니 "누가 언제 뭘 바꿨는지" 추적이 쉽다
- 롤백도 Git에서 revert하면 끝이다

## 다음에 할 것

- [ ] Python 웹앱 만들어서 ArgoCD로 배포
- [ ] Trivy로 컨테이너 이미지 보안 스캔
- [ ] Falco로 런타임 보안 감시
- [ ] Prometheus + Grafana 모니터링 대시보드
