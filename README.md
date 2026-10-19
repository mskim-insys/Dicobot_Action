# 📢 나라장터 IT/AI 공고 디스코드 알리미 (Discord Webhook 방식)

공공데이터포털의 **'조달청 나라장터 입찰공고정보서비스' API**를 활용하여, IT/SW/머신비전/AI/스마트공장 분야의 알짜 공고를 수집·필터링하고 **디스코드 웹훅(Discord Webhook)**으로 예쁜 카드 뉴스(Embed) 형태로 전송하는 프로젝트입니다.

퇴근 후 PC를 꺼두어도 **GitHub Actions(무료 크론 스케줄러)**를 통해 정해진 시간마다 자동으로 공고를 수집하여 디스코드로 전송합니다.

---

## 📁 프로젝트 구조

```text
workspace_dicobot/
├── .github/workflows/
│   └── koneps_notifier.yml   # [GitHub Actions] 매일 자동 실행 크론 워크플로우
├── .env                      # [설정] API 키 및 웹훅 URL 입력 파일 (Git에 업로드되지 않음)
├── .env.example              # [설정 예시] 템플릿 파일
├── .gitignore                # 보안 및 캐시 파일 제외 설정
├── requirements.txt          # 파이썬 의존성 패키지 목록
├── koneps_client.py          # 조달청 나라장터 API 호출 및 키워드/금액 스마트 필터 모듈
├── discord_webhook.py        # 디스코드 카드 뉴스(Embed) 포맷팅 및 웹훅 전송 모듈
├── main.py                   # 메인 실행 스크립트 (중복 방지 및 전체 파이프라인 제어)
└── sent_notices.json         # (자동 생성) 이미 전송 완료된 공고 번호 캐시 (중복 알림 방지)
```

---

## ⚙️ 1. 키 설정 방법 (.env 파일 작성)

프로젝트 루트의 [`.env`](file:///.env) 파일을 열고 발급받으신 정보를 입력해주세요:

```env
# 1. 공공데이터포털 일반 인증키 (Encoding 또는 Decoding 키 아무거나 입력)
DATA_GO_KR_API_KEY=발급받은_인증키_입력

# 2. 디스코드 웹훅 URL
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# 3. 타깃 필터링 키워드 (쉼표 구분)
TARGET_KEYWORDS=비전,머신비전,AI,인공지능,딥러닝,스마트,스마트팩토리,데이터,검사기,소프트웨어,SW

# 4. 금액 필터 사용 여부 (false: 금액 상관없이 모든 공고 알림 / true: 아래 금액 구간 적용)
ENABLE_PRICE_FILTER=false

# 금액 필터 구간 (ENABLE_PRICE_FILTER=true 일 때만 적용, 단위: 원)
MIN_PRICE=50000000
MAX_PRICE=1000000000

# 5. 조회 기간 (1 = 어제 00:00부터 오늘 23:59까지)
LOOKBACK_DAYS=1
```

### 💡 디스코드 웹훅 URL 생성 방법 (10초 소요)
1. 디스코드에서 알림을 받을 채널의 **[설정(톱니바퀴)]** 아이콘 클릭
2. **[연동(Integrations)]** -> **[웹후크(Webhooks)]** 클릭
3. **[새 웹후크 만들기]** 클릭 (봇 이름, 아바타 자유 변경 가능)
4. **[웹후크 URL 복사]** 버튼을 눌러 복사한 뒤, [`.env`](file:///.env)의 `DISCORD_WEBHOOK_URL=` 뒤에 붙여넣기

---

## 🚀 2. 로컬 실행 및 테스트 방법

### 1) 웹훅 디자인 및 알림 테스트 (API 키 없이도 바로 가능)
가상 공고 카드를 디스코드 채널로 1건 전송하여 웹훅이 정상 동작하는지 테스트합니다:
```bash
python main.py --test-webhook
```

### 2) 실제 공고 수집 및 전송 실행
`.env`에 두 키를 모두 입력한 후 실행합니다:
```bash
python main.py
```

### 3) 디스코드 전송 없이 수집 결과만 콘솔로 확인 (Dry Run)
```bash
python main.py --dry-run
```

### 4) 중복 검사 무시하고 강제 재전송
```bash
python main.py --force
```

### 5) 로컬에서 주기적으로 자동 실행 (예: 60분마다)
PC를 켜둔 상태에서 백그라운드로 주기적 실행을 돌릴 때 사용합니다:
```bash
python main.py --interval 60
```
*(또는 `.env`에 `INTERVAL_MINUTES=60`을 설정하고 `python main.py` 실행)*

---

## ☁️ 3. 퇴근 후 PC를 꺼도 자동 실행되게 하기 (GitHub Actions)

이 저장소를 GitHub에 Push해두면, 컴퓨터가 꺼져 있어도 GitHub 서버가 정해진 시간에 자동으로 스크립트를 실행합니다.

1. GitHub 저장소의 **[Settings]** -> **[Secrets and variables]** -> **[Actions]** 이동
2. **[New repository secret]**을 클릭하여 아래 2개 시크릿 등록:
   - `DATA_GO_KR_API_KEY`: 공공데이터포털 API 인증키
   - `DISCORD_WEBHOOK_URL`: 디스코드 웹훅 URL
3. `.github/workflows/koneps_notifier.yml`에 설정된 스케줄:
   - **한국 시간 기준 평일(월~금) 오전 9시, 오후 1시, 오후 5시** 자동 실행
   - 필요 시 GitHub의 **[Actions]** 탭에서 **'Run workflow'** 버튼을 눌러 수동 즉시 실행도 가능합니다.

