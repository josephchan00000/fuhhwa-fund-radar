# 2026-10-16 改寫 git 歷史（隱私）

> 2026-10-16 改寫整段 git 歷史：之後一律用 noreply 身分、舊 commit 編號已不存在、舊歷史的視窗不可再推、舊分支封存、PR 參照待 GitHub 客服清除。
> 原始資料：CLAUDE.md「已知環境限制與防呆（曾踩過的坑，不要再犯）」段第一條（該段的其他條見 [容器的限制](container.md)、[排程會話 MCP 審批](mcp-approval.md)）；程式：`tests/test_privacy.py`。
> 最後更新：2026-10-29
> 正本就是這一頁（2026-10-29 CLAUDE.md 瘦身時搬來；瘦身前全文 `git show d6ed51029:CLAUDE.md`）。

## 現在怎麼運作

- **改了什麼**（使用者要公開 repo 前說：「把我的名字跟email拿掉」）：
  - 早期 17 個 commit 作者欄的姓名、Gmail、Mac 主機名換成 `josephchan00000 <51159474+josephchan00000@users.noreply.github.com>`；
  - 檔案內容 `/Users/<名字>` 換成 `$HOME`、兩個 email 換成 `user@example.com`；
  - 工具：`git filter-repo --sensitive-data-removal --mailmap --replace-text`，2,141 個 commit 全部改寫，
    每個分支的檔案內容只差 `scripts/daily_run.sh`、`scripts/cf_publish.py` 各一行。
- **舊 commit 編號不存在了**：本檔與 docs 提到的舊編號（例 `21b5bcb`、`01767f9e7`）在分支上已不存在，新 main 從 `945a995cd` 起算。
- **分支現況（2026-10-16）**：擁有者已在 Mac 刪掉 90 個舊分支，GitHub 上只剩 `main`、`claude/etf-holdings-analysis-ui-0vkuak`、
  `claude/archive-old-branches`、`claude/all-update-45bep4`（都是新歷史，4 個沒合併的舊 PR 隨之關閉）。
- **舊分支封存**：91 個舊分支的改寫版都封存在 `claude/archive-old-branches`（每個「archive: 分支名」commit 的第二個 parent 就是該分支）。
- **repo 已公開**：2026-10-16 使用者為了 Actions 額度把 repo 改成公開（公開 repo 的一般機器不計分鐘，見 [GitHub Actions 額度](../ops/ci-budget.md)）。

### 還沒做完：PR 參照

GitHub 上的 PR 參照（`refs/pull/*`，使用者無法刪）還指向舊 commit，舊 PR 參照仍含舊歷史、尚未送客服。
要徹底清除就請 GitHub 客服處理，申請要附：first changed commit `67dffd35d05eb71f0f120c3b2c4b44cb2b78a819`（舊歷史的根 commit）、
受影響的 PR＝#1～#267（全部）。

原文另有一句「清除前不要把 repo 改成公開」；同日已為了 Actions 額度改公開，這一句已過時。

## 不能改的規則

- **之後所有 commit 一律用 noreply 身分**（CI 與 Claude 會話本來就是）；`tests/test_privacy.py` 守程式、設定、文件不出現個人 email 與本機使用者路徑。
- **本地還是舊歷史的視窗**（排程會話、舊對話）不可再推送舊分支或把 origin/main 合併進去（unrelated histories）；改寫後要「排程搬家」到新視窗
  （見 [排程與「排程搬家」](../ops/routines.md)）。
- **這個環境的 git proxy 擋推標籤、刪分支、一次推多個分支（HTTP 403）**，一次只能推一個分支——批次整理舊分支要由擁有者在自己電腦上做，
  不要一個一個推來繞過。

## 歷史

- 2026-10-16：使用者要公開 repo 前說「把我的名字跟email拿掉」→ 改寫整段歷史；擁有者在 Mac 刪掉 90 個舊分支、4 個沒合併的舊 PR 關閉；
  同日為了 Actions 額度把 repo 改成公開（PR 參照還沒送客服）。
