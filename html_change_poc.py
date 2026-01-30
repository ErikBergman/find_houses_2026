import json, requests, os
from datetime import datetime
from bs4 import BeautifulSoup
from lxml import etree

# 1. Load Config
with open("resources/config.json") as f:
    cfg = json.load(f)

try:
    # 2. Fetch and Parse
    headers = {"User-Agent": cfg.get("user_agent", "Mozilla/5.0")}
    res = requests.get(
        cfg['url'],
        headers=headers,
        timeout=cfg.get('timeout_seconds', 20),
    )
    res.raise_for_status()
    
    # We use lxml to find the XPath, then pass to BeautifulSoup for easy innerHTML
    dom = etree.HTML(res.text)
    matches = dom.xpath(cfg['xpath'])
    if not matches:
        raise ValueError(f"No elements matched XPath: {cfg['xpath']}")
    element = matches[0]
    inner_html = (element.text or "") + "".join(etree.tostring(child, encoding='unicode') for child in element)

    # 3. Log it
    os.makedirs(os.path.dirname(cfg['log_path']), exist_ok=True)
    with open(cfg['log_path'], "a", encoding="utf-8") as log:
        log.write(f"{datetime.now().isoformat()}\tOK\t{inner_html}\n")

except Exception as e:
    print(f"Failed: {e}")
