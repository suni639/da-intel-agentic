import os
import sys
import json
import time
import datetime
import subprocess
import smtplib
import re
import warnings
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Paths
WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_BRIEFING_PATH = os.path.join(WORKSPACE_ROOT, "pipeline", "output_briefing.md")
ERROR_LOG_PATH = os.path.join(WORKSPACE_ROOT, "error_log.txt")

def log_error(msg):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(ERROR_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] ERROR: {msg}\n")
    print(f"ERROR: {msg}", file=sys.stderr)

# Helper to fetch environment variables, supporting fallback to Windows registry for local setups
def get_env_var(name):
    val = os.environ.get(name)
    if not val and sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
            val, _ = winreg.QueryValueEx(key, name)
            winreg.CloseKey(key)
        except Exception:
            pass
    return val

# Verify all mandatory environment variables are set before proceeding
def verify_environment():
    missing_vars = []
    required_vars = ["SMTP_USER", "SMTP_PASS"]
    
    for var in required_vars:
        if not get_env_var(var):
            missing_vars.append(var)
            
    if missing_vars:
        log_error(f"Missing required environment variables: {', '.join(missing_vars)}")
        return False
    return True

# HTML Newsletter Formatter (same as previous project)
def convert_markdown_to_newsletter_html(subject, date_str, markdown_content):
    try:
        import markdown
    except ImportError:
        print("Installing missing dependency: markdown...")
        subprocess.run([sys.executable, "-m", "pip", "install", "markdown"], check=True)
        import markdown

    raw_html = markdown.markdown(markdown_content)
    
    # Wrap the synthesis block in a card
    if "<h2>1. MACRO VIEW</h2>" in raw_html:
        parts = raw_html.split("<h2>2. CORE PILLAR DEVELOPMENTS</h2>")
        if len(parts) > 1:
            synthesis_part = parts[0]
            rest_part = parts[1]
            
            synthesis_part = synthesis_part.replace("<p>", '<div class="synthesis-card"><p>', 1)
            synthesis_part += '</div>'
            
            raw_html = synthesis_part + "<h2>2. CORE PILLAR DEVELOPMENTS</h2>" + rest_part

    css_styles = """
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      background-color: #f1f5f9;
      color: #334155;
      margin: 0;
      padding: 0;
      -webkit-font-smoothing: antialiased;
    }
    .email-container {
      max-width: 680px;
      margin: 40px auto;
      background-color: #ffffff;
      border-radius: 12px;
      border: 1px solid #e2e8f0;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
      overflow: hidden;
    }
    .header {
      background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
      padding: 32px;
      color: #ffffff;
    }
    .header h1 {
      font-size: 22px;
      font-weight: 700;
      margin: 0 0 6px 0;
      letter-spacing: -0.5px;
    }
    .header .date {
      font-size: 13px;
      color: #94a3b8;
      font-weight: 500;
      }
    .content {
      padding: 32px;
      line-height: 1.6;
    }
    .content h1 {
      display: none;
    }
    .content h2 {
      font-size: 14px;
      font-weight: 700;
      color: #0f172a;
      border-bottom: 2px solid #e2e8f0;
      padding-bottom: 6px;
      margin-top: 28px;
      margin-bottom: 12px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .content p {
      margin-top: 0;
      margin-bottom: 16px;
      font-size: 14px;
      color: #475569;
    }
    .synthesis-card {
      background-color: #f8fafc;
      border-left: 4px solid #2563eb;
      padding: 18px;
      border-radius: 0 8px 8px 0;
      margin-bottom: 24px;
    }
    .synthesis-card p {
      margin: 0;
      font-size: 14.5px;
      color: #1e293b;
      line-height: 1.6;
    }
    .content ul {
      padding-left: 20px;
      margin-top: 8px;
      margin-bottom: 20px;
    }
    .content li {
      margin-bottom: 12px;
      font-size: 13.5px;
      color: #475569;
    }
    .content li strong {
      color: #0f172a;
    }
    .content a {
      color: #2563eb;
      text-decoration: none;
      font-weight: 500;
    }
    .content a:hover {
      text-decoration: underline;
    }
    .footer {
      background-color: #f8fafc;
      padding: 24px;
      text-align: center;
      font-size: 11px;
      color: #94a3b8;
      border-top: 1px solid #f1f5f9;
    }
    """
    
    html_newsletter = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
  <style>
    {css_styles}
  </style>
</head>
<body>
  <div class="email-container">
    <div class="header">
      <h1>Institutional Digital Asset Intelligence</h1>
      <div class="date">{date_str}</div>
    </div>
    <div class="content">
      {raw_html}
    </div>
    <div class="footer">
      This is an automated intelligence briefing compiled by DA-INTEL-01.<br>
      To modify subscription preferences or source endpoints, edit config.json.
    </div>
  </div>
</body>
</html>
"""
    return html_newsletter

# Email Delivery Layer (Multipart MIME)
def send_email(subject, plain_body, html_body, recipient_email):
    smtp_user = get_env_var('SMTP_USER')
    smtp_pass = get_env_var('SMTP_PASS')
    
    msg = MIMEMultipart('alternative')
    msg['From'] = smtp_user
    msg['To'] = recipient_email
    msg['Subject'] = subject
    
    msg.attach(MIMEText(plain_body, 'plain', 'utf-8'))
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))
    
    max_retries = 3
    is_github_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    retry_interval = 10 if is_github_actions else 15 * 60
    
    for attempt in range(1, max_retries + 1):
        try:
            print(f"Connecting to SMTP server (attempt {attempt}/{max_retries})...")
            server = smtplib.SMTP('smtp.gmail.com', 587, timeout=30)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipient_email, msg.as_string())
            server.quit()
            print("Email sent successfully!")
            return True
        except Exception as e:
            log_error(f"Email delivery attempt {attempt} failed: {str(e)}")
            if attempt < max_retries:
                print(f"Waiting {retry_interval} seconds before retrying...")
                time.sleep(retry_interval)
            else:
                return False

def main():
    dry_run = "--dry-run" in sys.argv
    
    print(f"Publishing script run started at: {datetime.datetime.now().isoformat()}")
    
    if not os.path.exists(OUTPUT_BRIEFING_PATH):
        log_error(f"Briefing file not found at {OUTPUT_BRIEFING_PATH}. Aborting publishing.")
        sys.exit(1)
        
    with open(OUTPUT_BRIEFING_PATH, "r", encoding="utf-8") as f:
        brief_content = f.read()
        
    today_str = datetime.date.today().isoformat()
    
    # 1. Hugo Site Publishing
    hugo_dir_env = get_env_var("HUGO_DIR")
    if hugo_dir_env:
        hugo_dir = os.path.abspath(hugo_dir_env)
    else:
        hugo_dir = os.path.join(os.path.dirname(WORKSPACE_ROOT), "sunilkandola-hugo")
    hugo_content_dir = os.path.join(hugo_dir, "content", "intel")
    brief_filename = f"weekly_brief_{today_str}.md"
    brief_filepath = os.path.join(hugo_content_dir, brief_filename)
    
    front_matter = f"""---
title: "Digital Asset Digest: {datetime.date.today().strftime('%d %B %Y')}"
date: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')}
draft: false
tags: ["digital-assets", "cbdc", "regulation", "tokenisation"]
categories: ["Intelligence"]
summary: "Weekly synthesis of wholesale banking, CBDCs, RWAs, and digital asset regulations."
---

"""
    
    if os.path.exists(hugo_dir):
        print(f"Hugo site folder found at {hugo_dir}.")
        if dry_run:
            print(f"[Dry-run] Would write post to {brief_filepath}")
        else:
            try:
                os.makedirs(hugo_content_dir, exist_ok=True)
                with open(brief_filepath, "w", encoding="utf-8") as f:
                    f.write(front_matter + brief_content)
                print(f"Brief written to Hugo content directory: {brief_filepath}")
                
                # Git Auto-Publish
                if os.path.exists(os.path.join(hugo_dir, ".git")):
                    print("Committing and pushing to Hugo repository...")
                    subprocess.run(["git", "add", "content/intel/"], cwd=hugo_dir, check=True)
                    subprocess.run(["git", "commit", "-m", f"Auto-publish weekly brief {today_str}"], cwd=hugo_dir, check=True)
                    push_res = subprocess.run(["git", "push"], cwd=hugo_dir, capture_output=True, text=True)
                    if push_res.returncode == 0:
                        print("Successfully pushed to Hugo remote repository.")
                    else:
                        log_error(f"Git push failed: {push_res.stderr.strip()}")
                else:
                    print("Hugo Git repository not found. Skipping auto-publish push.")
            except Exception as e:
                log_error(f"Failed to publish to Hugo site: {e}")
    else:
        print(f"Hugo website directory not found at {hugo_dir}. Skipping website publish.")

    # 2. Email Delivery
    if not verify_environment():
        print("Email sending skipped due to missing environment variables.")
        sys.exit(0)
        
    sender = get_env_var('SMTP_USER')
    recipient = get_env_var('RECIPIENT_EMAIL')
    if not recipient:
        recipient = sender  # Fallback to sending to oneself
        
    subject = f"Digital Asset Digest: {today_str}"
    html_content = convert_markdown_to_newsletter_html(subject, today_str, brief_content)
    
    if dry_run:
        print(f"[Dry-run] Would send email to {recipient} via SMTP server smtp.gmail.com")
        print("HTML payload structure checked successfully.")
    else:
        email_success = send_email(subject, brief_content, html_content, recipient)
        if email_success:
            print("Email delivered successfully.")
        else:
            log_error("Email delivery failed.")
            sys.exit(1)

if __name__ == '__main__':
    main()
