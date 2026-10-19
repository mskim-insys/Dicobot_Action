# 📢 디스코드 통합 알리미 (나라장터 공고 & IT 뉴스)

공공데이터포털의 **'조달청 나라장터 입찰공고'** 및 **'IT/AI 최신 뉴스'**를 정해진 시간마다 자동 수집하여 **디스코드 웹훅(Discord Webhook)**으로 예쁜 카드 뉴스(Embed) 형태로 전송하는 통합 알리미 봇 프로젝트입니다.

퇴근 후 PC를 꺼두어도 **GitHub Actions(무료 크론 스케줄러)**를 통해 정해진 시간마다 자동으로 공고와 뉴스를 수집하여 디스코드로 전송합니다.

---

## 📁 프로젝트 구조

```text
workspace_dicobot/
├── .github/workflows/
│   └── koneps_notifier.yml   # [GitHub Actions] 매일 자동 실행 크론 워크플로우 (Node 24 호환)
├── crawlers/                 # [크롤러 모음]
│   ├── koneps.py             # 나라장터 공고 수집 및 키워드/금액 스마트 필터
│   └── news.py               # IT/AI 뉴스 수집 모듈 (기획서 반영 대기 템플릿)
├── common/                   # [공통 모듈]
│   ├── discord_webhook.py    # 공통 디스코드 카드 뉴스(Embed) 포맷팅 및 웹훅 전송기
│   └── history.py            # 크롤러별 중복 방지 이력 관리자 (sent_history.json)
├── main.py                   # [통합 진입점] 전체 또는 특정 봇 파이프라인 제어
├── .env                      # [설정] API 키 및 웹훅 URL (Git 비공개)
├── .env.example              # [설정 예시] 템플릿 파일
├── .gitignore                # 보안 및 캐시 파일 제외 설정
├── requirements.txt          # 파이썬 의존성 패키지 목록
└── sent_history.json         # (자동 생성) 수집 완료된 항목 ID 캐시 (중복 알림 방지)
```

---

## ⚙️ 1. 환경 설정 (.env)

프로젝트 루트의 `.env` 파일에 필요한 키를 입력합니다:

```env
# 1. 디스코드 웹훅 URL (필수)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# (선택) 뉴스 전용 채널로 분리하고 싶을 때만 입력 (비워두면 위의 DISCORD_WEBHOOK_URL로 함께 전송)
DISCORD_NEWS_WEBHOOK_URL=

# 2. 나라장터 공공데이터포털 API 인증키
DATA_GO_KR_API_KEY=발급받은_인증키_입력

# 3. 나라장터 키워드 및 금액 필터
TARGET_KEYWORDS=비전,머신비전,AI,인공지능,딥러닝,스마트,스마트팩토리,데이터,검사기,소프트웨어,SW
ENABLE_PRICE_FILTER=false
MIN_PRICE=50000000
MAX_PRICE=1000000000
LOOKBACK_DAYS=1
```

---

## 🚀 2. 실행 및 테스트 방법

### 1) 웹훅 연결 테스트 (가상 카드 전송)
```bash
# 나라장터 + 뉴스 가상 카드 1건씩 전송 테스트
python main.py --test-webhook

# 나라장터 카드만 테스트
python main.py --test-webhook --target koneps

# 뉴스 카드만 테스트
python main.py --test-webhook --target news
```

### 2) 실제 수집 실행
```bash
# 전체(나라장터 + 뉴스) 순차 실행
python main.py

# 나라장터만 실행
python main.py --target koneps

# 뉴스만 실행
python main.py --target news
```

### 3) 디스코드 전송 없이 수집 결과만 콘솔로 확인 (Dry Run)
```bash
python main.py --dry-run
python main.py --target koneps --dry-run --force
```

### 4) 로컬에서 주기적으로 자동 실행 (예: 60분마다)
```bash
python main.py --interval 60
```

---

## ☁️ 3. GitHub Actions 자동 실행

저장소의 **[Settings] -> [Secrets and variables] -> [Actions]**에 아래 시크릿을 등록합니다:
* `DATA_GO_KR_API_KEY`: 공공데이터포털 인증키
* `DISCORD_WEBHOOK_URL`: 디스코드 웹훅 주소
* `DISCORD_NEWS_WEBHOOK_URL`: (선택) 뉴스 전용 웹훅 주소

스케줄 설정([`koneps_notifier.yml`](.github/workflows/koneps_notifier.yml)):
* **한국 시간 기준 평일(월~금) 오전 9시, 오후 1시, 오후 5시**에 `python main.py --target all` 자동 실행
* `sent_history.json` 파일에 중복 방지 이력을 자동 커밋하여 영구 보존
