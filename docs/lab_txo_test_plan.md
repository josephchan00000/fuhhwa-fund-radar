# 台指選擇權：給其他模型的驗收步驟（2026-11-05）

> 對象：拿到這個 repo 的另一個模型或測試者。目的：獨立檢查 2026-11-04～05 做的選擇權相關工作有沒有錯。
> **只檢查、只回報，不改程式、不改規格**（規格改了要 VER＋1，那是使用者決定的事）。規劃全文：`docs/lab_txo_plan.md`。
> 每一步都寫了「怎麼做」「應該看到什麼」。回報格式在最後。

---

## 0. 這次做了什麼（要驗收的範圍）

| PR | 內容 | 主要檔案 |
|---|---|---|
| #455 | 第 1 段：選擇權資料存檔（資料分支 `claude/txo-data`，絕不合併進 main） | `arm/lab/txodata.py`、`scripts/fetch_txo.py`、`.github/workflows/txo_data.yml`、`tests/test_txodata.py` |
| #456 | Vercel 部署儲存瘦身：`dashboard/` 跟上次成功部署一樣就不部署；資料分支放兩支 vercel.json | `vercel.json`、`dashboard/vercel.json`、`tests/test_multiuser_hardening.py` |
| #457 | 第 1 段結果文件＋第 2 段規格 `txospec` VER 1（還沒算任何成績） | `arm/lab/txospec.py`、`tests/test_txospec.py`、規劃第 15、16 節 |
| #458 | 計算機第 1 段：每晚的作戰表資料 `data/lab/txo_calc.json` | `arm/lab/txocalc.py`、`scripts/run_txocalc.py`、`tests/test_txocalc.py` |
| #459 | 計算機第 2 段：頁面 `x9op.html`、各頁右下角「選」字 | `arm/lab/txopage.py`、`arm/lab/appnav.py`、`tests/test_txopage.py` |

## 1. 規矩（照做，不然會誤判）

1. 容器連不到期交所、證交所、Vercel：**不要在容器裡跑任何抓取腳本**（`fetch_*.py`、`probe_*.py`）。要看線上資料就讀 CI 的日誌或資料分支。
2. 讀資料分支時**不要用 `git ls-tree -l`**（會逐檔下載內容，實測卡 30 分鐘）。要大小就看 CI 日誌的 `du -sh`。
3. 本機建出來的 `dashboard/*.html` **不要 commit**。
4. 時間一律台北時間（`TZ=Asia/Taipei`）。
5. 數字對不上時，先確認是不是「同一天、同一個口徑」再判錯。

---

## 2. 程式測試（容器內，約 15 分鐘）

```bash
git fetch origin main && git checkout origin/main      # 或 PR #459 的分支 claude/txo-page
pip install -q pytest
python3 -m pytest -q tests/test_txodata.py tests/test_txospec.py tests/test_txocalc.py tests/test_txopage.py tests/test_multiuser_hardening.py
python3 -m pytest -q                                    # 全部；跑完 git status data/ dashboard/ 應該沒有變動（有就 git checkout -- 還原）
```
**應該看到**：前五支全過；全部測試全過（2026-11-04 是 2,370 passed、2 skipped，數字會隨時間增加）。

## 3. 規格有沒有被偷改（容器內）

```bash
python3 -c "from arm.lab import txospec as S; print(S.VER, S.SPEC_DATE, S.fingerprint())"
git log --format='%h %ad %s' --date=iso -- arm/lab/txospec.py
```
**應該看到**：`1 2026-11-05 95b3382fa1b170ae`；`txospec.py` 只有一筆 commit（規格寫好就沒動過）。
**也要確認**：repo 裡還沒有任何「選擇權策略成績」的檔（例如 `data/lab/txo_research.json` 不存在）。第 3 段才會算。

## 4. 資料分支內容（容器內，讀 git，不連外網）

```bash
git fetch origin claude/txo-data
git ls-tree --name-only origin/claude/txo-data                                  # README.md bars day idx state.json（之後還會有 vercel.json、dashboard/）
git ls-tree -r --name-only origin/claude/txo-data | awk -F/ '{n[$1]++} END{for(k in n) print k, n[k]}'
git ls-tree --name-only origin/claude/txo-data day/ | sed -n '1p;$p'
```
**應該看到**：`day` 約 299 個月（2002-01 起到本月）、`idx` 約 2,631 天（2016-01-04 起）、`bars` 約 30 天以上（每個交易日多一天）。

**4.1 抽查一天的日行情**（解壓讀，不要跑抓取）
```bash
mkdir -p /tmp/txochk && git show origin/claude/txo-data:day/2026-11.json.gz > /tmp/txochk/day.gz
python3 -I -c "
import gzip,json; d=json.loads(gzip.decompress(open('/tmp/txochk/day.gz','rb').read()))
print(d['cols']); r=[x for x in d['rows'] if x[0]=='2026-11-04' and x[1]=='202611F1' and x[2] in (42500,42950)]; print(r)"
```
**應該看到**：欄位 `d exp k cp o h l c v s oi bid ask xd`；11/4 的 202611F1：42,500 賣權結算 336、42,950 買權 560／賣權 505，到期日 2026-11-06。
**要跟官方比**（需要能上期交所網站的人或模型）：期交所「每日交易行情查詢 → 選擇權」選 2026/11/04、TXO、202611F1，看這兩檔的結算價是否一樣。

**4.2 沒有 5 秒指數的日子都是休市**（用「那天選擇權有沒有成交」比；**不要用 `twholidays`**，它只有近兩年的休市表，拿來比歷史會誤判一大串）
```bash
git show origin/claude/txo-data:state.json > /tmp/txochk/state.json
python3 - <<'PY'
import json, gzip, subprocess
none = json.load(open('/tmp/txochk/state.json')).get('idx_none', [])
bad = []
for m in sorted({d[:7] for d in none}):
    b = subprocess.run(["git", "show", f"origin/claude/txo-data:day/{m}.json.gz"], capture_output=True).stdout
    days = {r[0] for r in json.loads(gzip.decompress(b))["rows"]}
    bad += [d for d in none if d[:7] == m and d in days]
print(len(none), "天記為沒有 5 秒指數；其中那天選擇權有成交的：", bad)
PY
```
**應該看到**：清單是空的（2026-11-05 實測：197 天、0 天有問題）。不是空的就是**錯誤**：那幾天會被永久跳過、不再重抓（要回報日期）。

**4.3 逐筆分 K 一天**
```bash
git ls-tree --name-only origin/claude/txo-data bars/2026/ | tail -3
git show origin/claude/txo-data:bars/2026/2026-11-04.json.gz > /tmp/txochk/b.gz
python3 -c "
import gzip,json; from arm.lab import txodata as T
d=json.loads(gzip.decompress(open('/tmp/txochk/b.gz','rb').read())); print(d['ref'], len(d['c']), sorted(d['exp'].items())[:4])
b=T.from_bars(d['c']['202611W1|P|42500']); print(b[0], max(x[2] for x in b), b[-1])"
```
**應該看到**：參考指數約 43,307；契約數幾百個；202611W1 42,500 賣權當天最高價約 560（規劃第 1.2 節：22 → 560 → 收盤歸零）。

## 5. 作戰表資料 `data/lab/txo_calc.json`（容器內）

```bash
python3 -c "
import json, math; from arm.lab import txocalc as C
d=json.load(open('data/lab/txo_calc.json')); print(d['asof'], d['next'], d['close'], d['atm'], d['atm_iv'], d['em'])
print('正常波動檢查', round(d['close']*d['atm_iv']/math.sqrt(252),1), '== em')
for e in d['exps']:
    r=[x for x in e['rows'] if x[0]==d['atm']]
    print(e['code'], e['date'], e['n'], e['tomorrow'], len(e['rows']), r)
    if r and r[0][1] and r[0][3]:
        print('  隱含指數水準 f', e.get('f'), ' 價平波動率 買權', r[0][2], ' 賣權', r[0][4])
"
```
**應該看到**：
- `asof` 是最近一個交易日、`next` 是它的下一個交易日（遇週末、休市要跳過）。
- `em` ＝ 收盤 × 價平波動率 ÷ √252（差 0.1 以內）。
- 每批到期 21 檔（價平上下各 10 檔，偶爾少於 21 是期交所沒掛那一檔）、`n`＝從 asof 到到期日的交易日數、明天到期的那批 `tomorrow=true`。
- 每批到期有 `f`（選擇權自己隱含的指數水準，＝價平附近 K＋C−P 的中位數）。選擇權 13:45 收、加權指數 13:30 收，所以 `f` 跟收盤差幾十點是正常的；
  到期越遠差越多（含股利、資金成本），月選差到兩三百點也可能。
- 價平那一檔買權、賣權的波動率（`rows` 的第 3、5 欄）應該很接近（差 1 個百分點以內）。差很多要回報。

**用資料分支重算一次**（確認每晚 CI 算的跟程式一致）：
```bash
mkdir -p /tmp/txochk/root/day /tmp/txochk/root/idx/2026
D=$(python3 -c "import json;print(json.load(open('data/lab/txo_calc.json'))['asof'])")
git show origin/claude/txo-data:day/${D:0:7}.json.gz > /tmp/txochk/root/day/${D:0:7}.json.gz
git show origin/claude/txo-data:idx/${D:0:4}/$D.json.gz > /tmp/txochk/root/idx/${D:0:4}/$D.json.gz
TZ=Asia/Taipei python3 scripts/run_txocalc.py --root /tmp/txochk/root --out /tmp/txochk/calc.json
python3 -c "import json; a=json.load(open('data/lab/txo_calc.json')); b=json.load(open('/tmp/txochk/calc.json')); print('一樣' if a==b else '不一樣')"
```
**應該看到**：「一樣」。（如果資料分支已經有更新的一天，`run_txocalc` 會算更新的那天；那就改看兩邊 asof 是否不同而已。）

## 6. 計算機頁面（容器內可以用 Playwright；也可以等上線後用手機看）

**6.1 建頁與截圖**
```bash
python3 -c "from arm.lab import txopage; print(txopage.build())"
node -e "
const {chromium}=require('playwright');(async()=>{const b=await chromium.launch();
for (const [w,h] of [[320,700],[390,844],[768,1024],[1200,900]]) { const p=await b.newPage({viewport:{width:w,height:h}});
const e=[]; p.on('pageerror',x=>e.push(x.message)); await p.goto('file://'+process.cwd()+'/dashboard/x9op.html'); await p.waitForTimeout(300);
console.log(w, '錯誤', e, '橫向捲動', await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth));
await p.screenshot({path:'/tmp/txochk/op_'+w+'.png', fullPage:true}); } await b.close(); })()"
git checkout -- dashboard/ 2>/dev/null; rm -f dashboard/x9op.html
```
**應該看到**：四種寬度都沒有錯誤、沒有橫向捲動。截圖要看：表格每列一行（不能有某一列變成直的一條）、價平那列粗體、按鈕不重疊。也切深色模式看一次（頁首的深淺色鈕）。

**6.2 用 11/4 收盤資料手算對答案**（`data/lab/txo_calc.json` 的 asof 若已不是 11/4，先用第 5 步的方法、把 `D` 設成 `2026-11-04` 重算一份 11/4 的作戰表，再用它建頁：
`python3 -c "import json; from arm.lab import txopage; txopage.build(data=json.load(open('/tmp/txochk/calc.json')))"`。
注意：`run_txocalc.py` 會挑資料夾裡最新的一天，所以 `/tmp/txochk/root` 只放 11/4 的兩個檔。）

| 操作 | 頁面應該顯示 | 手算 |
|---|---|---|
| 到期選「11/6 到期」、賣權、履約價 42,500，成交價 336，口數 1，帳戶 1,000,000，手續費 25，上限 O1 2% | 最多賠 **16,984 元**、占帳戶 **1.70%**、損益兩平 **42,164**、上限內最多 **1** 口 | 一邊成本＝25＋0.1%×336×50＋1 檔(1 點)×50＝91.8；336×50＋2×91.8＝16,983.6；42,500−336 |
| 同上，看情境表「−2%」那列、「11:30」那格 | 約 **+16,636**、約 **2.0 倍** | 指數 42,948.91×0.98，加上隱含指數水準的差距 (43,010−42,948.91)×(1.45÷2)；剩餘時間 (2−165/300)/252 年；波動 36.46%；Black-Scholes 賣權價約 672.4；(672.4−336)×50−2×91.8 |
| 同上，「−3%」那列「到期結算」 | 約 **+24,994** | 內含價值 42,500−41,660.4＝839.6；(839.6−336)×50−183.6 |
| 履約價改 42,950、成交價 505 | 最多賠 **25,851**、占帳戶 **2.59%**，兩格變紅框；上限內最多 **0** 口 | 505×50＋2×(25＋25.25＋5×50)；超過 2% |
| 成交價改 22、口數清空讓它自動算 | 口數 16、最多賠 **19,235**、跌一半停損 **10,426** | 一口全成本 22×50＋2×51.1＝1,202.2；20,000÷1,202.2＝16 口；停損＝16×(11×50＋51.1＋50.55) |

**6.3 互動**：點作戰表任一列 → 上面的履約價、成交價跟著變、頁面捲回上方；換「買權／賣權」、換到期日 → 數字重算；
重新整理頁面 → 帳戶金額、手續費、上限還在（存在瀏覽器）；成交價打字母或負數 → 不應該壞掉（保持原值）。

**6.4 過期標記**：把電腦日期設成作戰表 `next` 之後的日子（或改 JSON 的 `next` 成過去的日期再建頁）→ 頁面最上面要出現紅色「作戰表停在…還沒更新到今天」。

**6.5 右下角「選」字**（上線後在手機看最準）：打開 `x9m.html`、`x9.html`、`x9r.html`、`x9mu.html`，右下角都有一個小圓圈「選」，點了到計算機；
計算機頁自己沒有；不能擋住其他按鈕或抽屜（例如市場頁「之後怎麼走」側邊抽屜打開時）；列印預覽看不到它。

## 7. CI 與上線（需要能看 GitHub Actions；交易日晚上 19:30 以後檢查）

1. `txo_data.yml` 當天 18:35（或 22:05 兜底）那一輪 **success**；日誌裡「作戰表」那一步印「[txocalc] {今天} 收盤 …」；
   main 上多一筆「chore: 選擇權作戰表 …」commit，改了 `data/lab/txo_calc.json`（和 `dashboard/x9op.html`）。
2. 資料分支多一筆「chore: 台指選擇權資料 …」，`bars/{年}/{今天}.json.gz` 出現；那一筆 commit 根目錄有 `vercel.json` 和 `dashboard/vercel.json`。
3. 週末、休市日：不應該產生新的分 K 檔；作戰表不變；workflow 不應該紅。
4. Vercel：
   - `daily.yml`／`afterhours_refresh.yml` 的「對時哨兵」步驟仍然 ✅（印「部署已生效」）。
   - Vercel Deployments 裡，只改 `data/` 的 main commit 應該顯示 Canceled（Ignored Build Step）。
   - 改到 `dashboard/` 的照常部署。
5. 資料分支有 push 時，不應再收到 Vercel「Preview deployment failed」信（11/5 以後的 commit）。

## 8. 我自己先檢查出來、已經修掉的（給測試者參考，請再確認一次）

1. **作戰表的波動率有時間差**：選擇權 13:45 收盤、加權指數 13:30 收盤，原本直接用指數收盤反推，11/4 價平買權 37%、賣權 33%（差 4 個百分點，大部分是假的）。
   改成先用買賣權平價找出選擇權自己隱含的指數水準 `f` 再反推（`txocalc` VER 2），兩邊變成 34.7%／35.0%；情境表也把這段差距算進去、到到期收斂成 0。
2. **「跌一半就停損時賠」的成本少算**：原本兩邊都用半價算手續費與稅，改成買進用原價、賣出用半價。
3. **作戰表過期沒有標記**：CI 哪天沒更新，頁面會默默用舊數字。現在瀏覽器日期晚於作戰表的「下一個交易日」就在最上面掛紅字。
4. **頁面表格某一列變直的**：價平那一列的 class 跟別頁的樣式撞名，改成 `op` 開頭的名字。
5. 檢查過、**沒問題**的：5 秒指數記為「沒有資料」的 197 天，全部是選擇權也沒成交的休市日；`txospec` 從寫好之後沒有被改過；目前沒有任何策略成績檔。

## 9. 已知限制（不要當成錯誤回報）

- 計算機的情境表用**公式估算**（Black-Scholes、無風險利率 0），不是真的成交價；越價外、越接近到期，誤差越大。
- 「最多賠」把賣出那一邊的成本也算進去（就算放到到期歸零不用賣），所以略高一點，是刻意保守。
- 結算日的實際結算價是 13:00～13:30 平均，表上的「到期結算」用「指數停在那裡」近似。
- 波動率是用前一天的**結算價**反推，冷門履約價（未平倉很少）可能怪怪的。
- 還沒有盤中即時報價（下一段才做探針）；不做夜盤。
- 策略成績一個都還沒算：規格 VER 1 寫好了，第 3 段才回測。
- 資料分支 `claude/ussx-data`、`claude/txo-data` 絕不合併進 main。

## 10. 回報格式

| 步驟 | 結果（過／不過／沒辦法測） | 證據（指令輸出、截圖檔名、run 編號） | 備註 |
|---|---|---|---|
| 2 程式測試 | | | |
| 3 規格沒動 | | | |
| 4.1～4.3 資料分支 | | | |
| 5 作戰表 | | | |
| 6.1～6.5 頁面 | | | |
| 7 CI 與上線 | | | |

另外列出：你覺得**可能錯但不確定**的地方（附理由），和**沒測到**的步驟與原因。
