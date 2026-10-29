---
paths:
  - "arm/lab/company.py"
  - "arm/lab/copage.py"
  - "arm/lab/fcst.py"
  - "arm/lab/industry.py"
  - "scripts/fetch_fcst.py"
---
改公司分析或法人預估之前，先讀 `wiki/lab/company.md`、`wiki/lab/forecast.md`。
- 「目標價」只准出現在 `tests/test_fcst.py::FC_FUNCS` 那幾支 JS 函式；FactSet 快訊標題不轉載。
- copage 的 JS 插在頁面初始化之前（頂層 const 會 TDZ）；會在初始化時呼叫的函式別用頂層 const。
