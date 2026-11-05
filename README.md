# 📢 디스코드 통합 알리미 (나라장터 공고 & 테크 뉴스)

공공데이터포털의 **조달청 나라장터 입찰공고**, 긱뉴스·Hacker News, OpenAI News·Simon Willison·Lobsters RSS/Atom 피드, Arxiv 및 Hugging Face Daily Papers 논문을 정해진 시간마다 수집하여 **디스코드 웹훅(Discord Webhook)**으로 Embed 형태로 전송합니다. 각 뉴스 소스는 서로 다른 Discord 채널로 분리할 수 있습니다.

퇴근 후 PC를 꺼두어도 **GitHub Actions(무료 크론 스케줄러)**를 통해 정해진 시간마다 자동으로 공고와 뉴스를 수집하여 디스코드로 전송합니다.

---

## 📁 프로젝트 구조

```text
workspace_dicobot/
├── .github/workflows/
│   └── koneps_notifier.yml   # [GitHub Actions] 매일 자동 실행 크론 워크플로우 (Node 24 호환)
├── crawlers/                 # [크롤러 모음]
│   ├── koneps.py             # 나라장터 공고 수집 및 키워드/금액 스마트 필터
│   ├── news.py               # 긱뉴스 및 OpenAI/Simon Willison/Lobsters RSS·Atom
│   ├── hackernews.py        # Hacker News 인기글
│   ├── arxiv.py             # AI/컴퓨터 비전 논문
│   └── huggingface.py       # Hugging Face Daily Papers REST API
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
# 1. 공통 fallback 웹훅 (선택, 태그별 채널만 쓸 경우 생략 가능)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# (선택) 나라장터 기본 채널 및 태그별 채널
DISCORD_KONEPS_WEBHOOK_URL=
DISCORD_KONEPS_MANUFACTURING_WEBHOOK_URL=
DISCORD_KONEPS_FOREIGN_WORKER_WEBHOOK_URL=
DISCORD_KONEPS_INDUSTRIAL_SAFETY_WEBHOOK_URL=

# (선택) 기본 뉴스 웹훅. 소스별 웹훅 미설정 시 적용
DISCORD_NEWS_WEBHOOK_URL=

# (선택) 피드별 개별 채널 웹훅. 비워두면 DISCORD_NEWS_WEBHOOK_URL,
# 그것도 비어 있으면 DISCORD_WEBHOOK_URL을 사용
DISCORD_OPENAI_WEBHOOK_URL=
DISCORD_SIMON_WILLISON_WEBHOOK_URL=
DISCORD_LOBSTERS_WEBHOOK_URL=
# Hugging Face는 전용 웹훅이 없으면 DISCORD_ARXIV_WEBHOOK_URL,
# 그것도 비어 있으면 DISCORD_WEBHOOK_URL을 사용
DISCORD_HUGGINGFACE_WEBHOOK_URL=

# 2. 나라장터 공공데이터포털 API 인증키
DATA_GO_KR_API_KEY=발급받은_인증키_입력

# 3. 나라장터 키워드 및 금액 필터
TARGET_KEYWORDS=비전,머신비전,AI,인공지능,딥러닝,스마트,스마트팩토리,데이터,검사기,소프트웨어,SW
KONEPS_MANUFACTURING_KEYWORDS=외관검사,머신비전,스마트공장,불량 선별,조립 검사,제조 AI
KONEPS_FOREIGN_WORKER_KEYWORDS=외국인 근로자,계절근로자,E-8,인력중개,근태관리,노무 도급,일자리 매칭
KONEPS_INDUSTRIAL_SAFETY_KEYWORDS=중대재해,작업자 안전,안전모 미착용,끼임 방지,위험구역 감시
ENABLE_PRICE_FILTER=false
MIN_PRICE=50000000
MAX_PRICE=1000000000
LOOKBACK_DAYS=1

# 피드별 수집 개수 (기본 5)
OPENAI_LIMIT=5
SIMON_WILLISON_LIMIT=5
LOBSTERS_LIMIT=5

# Hugging Face Daily Papers (기본 5개, 날짜/키워드는 선택)
HF_DAILY_PAPERS_LIMIT=5
HF_DAILY_PAPERS_DATE=
# HF_DAILY_PAPERS_KEYWORDS=vision,llm,diffusion

# 4. 기능별 실행 여부 (true/false, 생략하면 true)
ENABLE_KONEPS=true
ENABLE_GEEKNEWS=true
ENABLE_HACKERNEWS=true
ENABLE_ARXIV=true
ENABLE_HUGGINGFACE=true
ENABLE_OPENAI=true
ENABLE_SIMON_WILLISON=true
ENABLE_LOBSTERS=true
```

`ENABLE_...=false`로 설정한 기능은 전체 실행(`--target all`/`news`)과 웹훅 테스트에서 제외됩니다. `true` 또는 `false`를 지정하고, 생략 시 기존 동작을 유지하도록 기본 활성화됩니다. GitHub Actions에서는 같은 이름의 Repository Variables를 설정할 수 있으며, 미설정 시 활성화됩니다.

나라장터는 `KONEPS_MANUFACTURING`, `KONEPS_FOREIGN_WORKER`, `KONEPS_INDUSTRIAL_SAFETY` 세 키워드 그룹으로 공고를 분류합니다. 그룹별 웹훅이 설정된 경우 해당 채널로 보내며, 설정하지 않은 그룹은 `DISCORD_KONEPS_WEBHOOK_URL` 또는 공통 `DISCORD_WEBHOOK_URL`을 사용합니다. 여러 그룹에 동시에 맞는 공고는 각 그룹 채널로 전송하고, 같은 웹훅 URL이 여러 그룹에 설정된 경우 중복 전송하지 않습니다. 어느 분류에도 맞지 않는 기존 `TARGET_KEYWORDS` 공고는 기본 나라장터 채널로 전송됩니다. 그룹 키워드는 `.env` 또는 GitHub Actions Repository Variables에서 조정할 수 있습니다.

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

# 새 RSS/Atom 피드만 실행
python main.py --target openai
python main.py --target simonwillison
python main.py --target lobsters
python main.py --target huggingface
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
* `DISCORD_KONEPS_WEBHOOK_URL`: (선택) 나라장터 기본 채널 웹훅
* `DISCORD_KONEPS_MANUFACTURING_WEBHOOK_URL`, `DISCORD_KONEPS_FOREIGN_WORKER_WEBHOOK_URL`, `DISCORD_KONEPS_INDUSTRIAL_SAFETY_WEBHOOK_URL`: (선택) 나라장터 태그별 채널 웹훅
* `DISCORD_NEWS_WEBHOOK_URL`: (선택) 뉴스 전용 웹훅 주소
* `DISCORD_OPENAI_WEBHOOK_URL`, `DISCORD_SIMON_WILLISON_WEBHOOK_URL`, `DISCORD_LOBSTERS_WEBHOOK_URL`: (선택) 피드별 전용 웹훅 주소
* `DISCORD_HUGGINGFACE_WEBHOOK_URL`: (선택) Hugging Face 논문 전용 웹훅 주소. 비우면 `DISCORD_ARXIV_WEBHOOK_URL`, 그것도 비우면 `DISCORD_WEBHOOK_URL`을 사용합니다.

태그별 키워드를 바꾸려면 Repository Variables에 `KONEPS_MANUFACTURING_KEYWORDS`, `KONEPS_FOREIGN_WORKER_KEYWORDS`, `KONEPS_INDUSTRIAL_SAFETY_KEYWORDS`를 설정합니다. 쉼표로 키워드를 구분하며, 생략 시 기본 키워드를 사용합니다.

기능을 끄려면 Repository Variables에 `ENABLE_KONEPS`, `ENABLE_GEEKNEWS`, `ENABLE_HACKERNEWS`, `ENABLE_ARXIV`, `ENABLE_HUGGINGFACE`, `ENABLE_OPENAI`, `ENABLE_SIMON_WILLISON`, `ENABLE_LOBSTERS` 중 해당 변수에 `false`를 지정합니다. 설정하지 않은 기능은 활성화됩니다.

Hugging Face Daily Papers API는 공개 읽기 API이므로 별도 API 키가 필요하지 않습니다. 날짜를 지정하지 않으면 API의 기본 최신 목록을 가져오며, `HF_DAILY_PAPERS_DATE`에 `YYYY-MM-DD`를 설정하면 해당 날짜를 조회합니다.

스케줄 설정([`koneps_notifier.yml`](.github/workflows/koneps_notifier.yml)):
* **한국 시간 기준 평일(월~금) 오전 9시, 오후 1시, 오후 5시**에 `python main.py --target all` 자동 실행
* `sent_history.json` 파일에 중복 방지 이력을 자동 커밋하여 영구 보존
