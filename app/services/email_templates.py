"""
Shared email HTML template: Ministry branding, responsive layout, system light/dark theme.
Logo uses hosted URL so it loads reliably in email clients.
"""
from typing import Optional

# Hosted logo – use URL so it displays in email inbox (no local file path)
LOGO_URL = "https://verify-mwhwr.vercel.app/_next/image?url=%2Fministry-1.png&w=1920&q=75"


def wrap_email_body(
    title: str,
    body_html: str,
    button_text: Optional[str] = None,
    button_link: Optional[str] = None,
) -> str:
    """
    Wrap content in the shared layout: logo, responsive container, light/dark theme.
    body_html is inserted inside the main content area; optional CTA button below.
    """
    button_block = ""
    if button_text and button_link:
        button_block = f"""
        <p style="margin: 24px 0 0 0;">
          <a href="{button_link}" class="btn-primary" style="
            display: inline-block;
            padding: 12px 24px;
            background: var(--accent);
            color: #fff !important;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 16px;
          ">{button_text}</a>
        </p>
        """

    return f"""<!DOCTYPE html>
<html lang="en" style="margin:0;padding:0;">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="light dark">
  <meta name="supported-color-schemes" content="light dark">
  <title>{title}</title>
  <style type="text/css">
    :root {{
      --bg: #f8fafc;
      --surface: #ffffff;
      --text: #1e293b;
      --text-muted: #64748b;
      --accent: #033783;
      --border: #e2e8f0;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #0f172a;
        --surface: #1e293b;
        --text: #f1f5f9;
        --text-muted: #94a3b8;
        --accent: #3b82f6;
        --border: #334155;
      }}
    }}
    body {{
      margin: 0;
      padding: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
      font-size: 16px;
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
    }}
    .wrapper {{
      width: 100%;
      max-width: 600px;
      margin: 0 auto;
      padding: 24px 16px;
      box-sizing: border-box;
    }}
    .card {{
      background: var(--surface);
      border-radius: 12px;
      border: 1px solid var(--border);
      padding: 32px 24px;
      margin-top: 24px;
    }}
    .logo {{
      display: block;
      max-width: 100%;
      height: auto;
      margin: 0 auto;
    }}
    h1 {{
      margin: 0 0 16px 0;
      font-size: 22px;
      font-weight: 700;
      color: var(--text);
    }}
    p {{
      margin: 0 0 12px 0;
      color: var(--text);
    }}
    .muted {{
      color: var(--text-muted);
      font-size: 14px;
    }}
    a {{
      color: var(--accent);
    }}
    @media (max-width: 480px) {{
      .card {{ padding: 24px 16px; }}
      .wrapper {{ padding: 16px 12px; }}
    }}
  </style>
</head>
<body>
  <div class="wrapper">
    <img src="{LOGO_URL}" alt="Ministry of Works, Housing &amp; Water Resources" class="logo" width="280" height="auto" style="max-width:280px;height:auto;" />
    <div class="card">
      <h1>{title}</h1>
      <div class="content">
        {body_html}
      </div>
      {button_block}
    </div>
    <p class="muted" style="margin-top: 24px; text-align: center;">
      Ministry of Works, Housing &amp; Water Resources (MWHWR)
    </p>
  </div>
</body>
</html>"""
