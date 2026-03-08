# Jay's DevOps Lab

공부하면서 직접 구축해본 것들을 정리하는 공간입니다.
클라우드에 바로 올리기 전에 로컬에서 충분히 만져보고 이해하자는 취지로 시작했습니다.

## 현재 진행 중인 프로젝트

### Local Kubernetes on Docker
Docker 위에 Kind로 멀티노드 K8s 클러스터를 올리고, 보안까지 직접 세팅해봤습니다.

- Control Plane 1대 + Worker 2대
- Nginx Ingress Controller로 트래픽 라우팅
- NetworkPolicy, RBAC, Pod Security Standards 적용
- Kubernetes Dashboard + k9s로 모니터링
- ArgoCD로 GitOps 자동 배포 구축
- Falco로 런타임 보안 감시 (커스텀 탐지 룰 포함)
- Ollama + Garak으로 LLM 보안 테스트
- FastAPI LLM 보안 프록시 (입출력 검증)

구축 과정을 글로 정리했습니다:
- [K8s 환경 구축](docs/01-k8s-local-setup.md)
- [ArgoCD GitOps 구축](docs/02-argocd-gitops.md)
- [Falco 런타임 보안](docs/03-falco-runtime-security.md)
- [Ollama + Garak AI 보안](docs/04-ollama-garak-ai-security.md)
- [LLM 보안 프록시](docs/05-llm-proxy.md)
- [전체 학습 가이드](docs/00-full-guide.md)

### Python 개발 환경 (세팅 완료)
추후 K8s 위에 올릴 앱을 만들 예정입니다.

## 사용 기술

`Docker` `Kubernetes` `Kind` `Helm` `k9s` `Nginx Ingress` `ArgoCD` `Falco` `Ollama` `Garak` `FastAPI` `Python` `VS Code`

## 폴더 구조

```
.
├── docs/                        # 구축 과정 정리 글
│   ├── 00-full-guide.md         # 전체 학습 가이드
│   ├── 01-k8s-local-setup.md    # K8s 구축 과정
│   ├── 02-argocd-gitops.md      # ArgoCD 구축 과정
│   ├── 03-falco-runtime-security.md  # Falco 런타임 보안
│   ├── 04-ollama-garak-ai-security.md  # Ollama + Garak AI 보안
│   └── 05-llm-proxy.md         # LLM 보안 프록시
├── argocd/                      # ArgoCD Application 설정
│   ├── sample-nginx-app.yaml
│   ├── falco-app.yaml
│   ├── ollama-app.yaml
│   └── llm-proxy-app.yaml
├── falco/                       # Falco 설정
│   ├── values.yaml
│   └── custom-rules.yaml
├── apps/                        # ArgoCD가 배포하는 앱들
│   ├── sample-nginx/
│   ├── ollama/
│   └── llm-proxy/
├── k8s/                         # K8s 설정 파일들
│   ├── kind-config.yaml
│   └── security/
│       ├── network-policy.yaml
│       ├── rbac.yaml
│       ├── pod-security.yaml
│       └── dashboard-admin.yaml
├── k8s-setup-plan.md            # 구축 결과 정리
└── python/
    └── llm-proxy/               # FastAPI LLM 보안 프록시 소스
```

## 따라해보기

Docker Desktop이 설치되어 있다는 전제입니다.

```bash
# 도구 설치 (Mac 기준)
brew install kind kubectl helm k9s

# 클러스터 띄우기
kind create cluster --config k8s/kind-config.yaml

# 보안 정책 적용
kubectl apply -f k8s/security/

# Ingress Controller 설치
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml

# 잘 떴는지 확인
kubectl get nodes
```

## 앞으로 할 것들

- [x] ArgoCD로 GitOps 자동 배포 구축
- [x] Falco 런타임 보안 감시 + 커스텀 룰
- [x] Ollama + Garak으로 LLM 보안 테스트
- [x] FastAPI LLM 보안 프록시 구축 (입출력 검증)
- [ ] Python 앱 만들어서 ArgoCD로 배포해보기
- [ ] Trivy로 컨테이너 이미지 보안 스캔
- [ ] Prometheus + Grafana 모니터링 붙이기
- [ ] GitHub Actions CI/CD 연동
