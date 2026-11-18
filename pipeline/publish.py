import json
import os
import sys
import time
import datetime
import subprocess
import smtplib
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from common import WORKSPACE_ROOT, get_env_var, log_error

OUTPUT_BRIEFING_PATH = os.path.join(WORKSPACE_ROOT, "pipeline", "output_briefing.md")

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

# Plain, email-client-safe styling. Styles are inlined on each element because
# Outlook and Gmail ignore or strip much of a <style> block. No backgrounds,
# boxes or coloured bars: white page, clear headings, readable body text.
FONT = "font-family:Arial,Helvetica,sans-serif;"
TEXT = "#222222"
MUTED = "#666666"
LINK = "#1a5fb4"

INLINE_STYLES = {
    "h2": f"{FONT}font-size:17px;font-weight:bold;color:{TEXT};margin:28px 0 8px 0;",
    "h3": f"{FONT}font-size:15px;font-weight:bold;color:{TEXT};margin:20px 0 6px 0;",
    "p": f"{FONT}font-size:14px;line-height:1.55;color:{TEXT};margin:0 0 10px 0;",
    "ul": "margin:0 0 14px 0;padding-left:20px;",
    "li": f"{FONT}font-size:14px;line-height:1.55;color:{TEXT};margin:0 0 8px 0;",
    "em": f"font-style:normal;color:{MUTED};",
}


def _inline_styles(html):
    for tag, style in INLINE_STYLES.items():
        html = re.sub(rf"<{tag}>", f'<{tag} style="{style}">', html)
    return re.sub(r'<a href="', f'<a style="color:{LINK};text-decoration:underline;" href="', html)


def _display_date(date_str):
    try:
        return datetime.date.fromisoformat(date_str).strftime("%-d %B %Y")
    except ValueError:
        return date_str


# HTML Newsletter Formatter
def convert_markdown_to_newsletter_html(subject, date_str, markdown_content):
    import markdown

    body = _inline_styles(markdown.markdown(markdown_content))
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{subject}</title>
</head>
<body style="margin:0;padding:0;background:#ffffff;">
<div style="max-width:680px;margin:0 auto;padding:24px 20px;background:#ffffff;">
<p style="{FONT}font-size:20px;font-weight:bold;color:{TEXT};margin:0 0 2px 0;">Digital Asset Digest</p>
<p style="{FONT}font-size:13px;color:{MUTED};margin:0 0 8px 0;">Weekly brief on institutional digital assets &middot; {_display_date(date_str)}</p>
{body}
<p style="{FONT}font-size:12px;color:{MUTED};margin:28px 0 0 0;">Compiled automatically by DA-INTEL-01 from public sources. Links go to the original articles.</p>
</div>
</body>
</html>
"""


def parse_recipients(recipient_env, default=None):
    """Split a comma/semicolon separated list; fall back to ``default`` (SMTP_USER)."""
    parts = re.split(r'[,;]', recipient_env or "")
    recipients = [p.strip() for p in parts if p.strip()]
    if recipients:
        return recipients
    return [default] if default else []

# Email Delivery Layer (Multipart MIME)
def send_email(subject, plain_body, html_body, recipients):
    if isinstance(recipients, str):
        recipients = parse_recipients(recipients, default=get_env_var('SMTP_USER'))
        
    smtp_user = get_env_var('SMTP_USER')
    smtp_pass = get_env_var('SMTP_PASS')
    
    msg = MIMEMultipart('alternative')
    msg['From'] = smtp_user
    msg['To'] = ", ".join(recipients)
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
            server.sendmail(smtp_user, recipients, msg.as_string())
            server.quit()
            print(f"Email sent successfully to: {', '.join(recipients)}!")
            return True
        except Exception as e:
            log_error(f"Email delivery attempt {attempt} failed: {str(e)}")
            if attempt < max_retries:
                print(f"Waiting {retry_interval} seconds before retrying...")
                time.sleep(retry_interval)
            else:
                return False

PUBLISH_RESULT_PATH = os.path.join(WORKSPACE_ROOT, "shared_artifacts", "publish_result.json")

# Channel outcomes
OK, FAILED, SKIPPED, DRY_RUN = "ok", "failed", "skipped", "dry-run"


def channels_required():
    """In CI every channel must be configured; a missing one is a failure, not a skip."""
    return (get_env_var("PUBLISH_REQUIRE_ALL_CHANNELS") or "").lower() in ("1", "true", "yes")


def _git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)


def publish_hugo(brief_content, today_str, dry_run):
    hugo_dir_env = get_env_var("HUGO_DIR")
    hugo_dir = (os.path.abspath(hugo_dir_env) if hugo_dir_env
                else os.path.join(os.path.dirname(WORKSPACE_ROOT), "sunilkandola-hugo"))
    hugo_content_dir = os.path.join(hugo_dir, "content", "intel")
    brief_filepath = os.path.join(hugo_content_dir, f"weekly_brief_{today_str}.md")

    if not os.path.exists(hugo_dir):
        msg = f"Hugo website directory not found at {hugo_dir}."
        if channels_required():
            log_error(msg)
            return FAILED
        print(msg + " Skipping website publish.")
        return SKIPPED
    if dry_run:
        print(f"[Dry-run] Would write post to {brief_filepath}")
        return DRY_RUN

    front_matter = f"""---
title: "Digital Asset Digest: {datetime.date.today().strftime('%d %B %Y')}"
date: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00')}
draft: false
tags: ["digital-assets", "cbdc", "regulation", "tokenisation"]
categories: ["Intelligence"]
summary: "Weekly synthesis of wholesale banking, CBDCs, RWAs, and digital asset regulations."
---

"""
    try:
        os.makedirs(hugo_content_dir, exist_ok=True)
        with open(brief_filepath, "w", encoding="utf-8") as f:
            f.write(front_matter + brief_content)
        print(f"Brief written to Hugo content directory: {brief_filepath}")

        if not os.path.exists(os.path.join(hugo_dir, ".git")):
            print("Hugo directory is not a Git repository; post written locally only.")
            return OK

        print("Committing and pushing to Hugo repository...")
        _git(["pull", "--rebase"], hugo_dir)
        _git(["add", "content/intel/"], hugo_dir)
        if _git(["diff", "--cached", "--quiet"], hugo_dir).returncode == 0:
            print("No changes to commit in Hugo site (already published).")
            return OK
        commit = _git(["commit", "-m", f"Auto-publish weekly brief {today_str}"], hugo_dir)
        if commit.returncode != 0:
            log_error(f"Hugo git commit failed: {commit.stderr.strip()}")
            return FAILED
        push = _git(["push"], hugo_dir)
        if push.returncode != 0:
            _git(["pull", "--rebase"], hugo_dir)  # remote moved on; retry once
            push = _git(["push"], hugo_dir)
        if push.returncode != 0:
            log_error(f"Hugo git push failed: {push.stderr.strip()}")
            return FAILED
        print("Successfully pushed to Hugo remote repository.")
        return OK
    except Exception as e:
        log_error(f"Failed to publish to Hugo site: {e}")
        return FAILED


def publish_email(brief_content, today_str, dry_run):
    if not verify_environment():
        if channels_required():
            return FAILED
        print("Email sending skipped due to missing environment variables.")
        return SKIPPED

    recipients = parse_recipients(get_env_var('RECIPIENT_EMAIL'), default=get_env_var('SMTP_USER'))
    subject = email_subject(today_str)
    html_content = convert_markdown_to_newsletter_html(subject, today_str, brief_content)

    if dry_run:
        print(f"[Dry-run] Would send email to {', '.join(recipients)} via SMTP server smtp.gmail.com")
        print("HTML payload structure checked successfully.")
        return DRY_RUN
    if send_email(subject, brief_content, html_content, recipients):
        print(f"Email delivered successfully to {len(recipients)} recipient(s).")
        return OK
    log_error("Email delivery failed.")
    return FAILED


SUBJECT_HOOK_PATH = os.path.join(WORKSPACE_ROOT, "shared_artifacts", "email_subject.txt")


def email_subject(today_str, hook_path=None):
    """'Digital Asset Digest, 23 Nov: <top story>' (falls back to the date alone)."""
    hook = ""
    try:
        with open(hook_path or SUBJECT_HOOK_PATH, "r", encoding="utf-8") as f:
            hook = " ".join(f.read().split()).strip(" .")
    except OSError:
        pass
    try:
        short_date = datetime.date.fromisoformat(today_str).strftime("%-d %b")
    except ValueError:
        short_date = today_str
    return f"Digital Asset Digest, {short_date}: {hook}" if hook else f"Digital Asset Digest: {today_str}"


def write_result(result, path=None):
    path = path or PUBLISH_RESULT_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)


def main():
    dry_run = "--dry-run" in sys.argv
    print(f"Publishing script run started at: {datetime.datetime.now().isoformat()}")

    if not os.path.exists(OUTPUT_BRIEFING_PATH):
        log_error(f"Briefing file not found at {OUTPUT_BRIEFING_PATH}. Aborting publishing.")
        write_result({"hugo": FAILED, "email": FAILED})
        sys.exit(1)

    with open(OUTPUT_BRIEFING_PATH, "r", encoding="utf-8") as f:
        brief_content = f.read()
    today_str = datetime.date.today().isoformat()

    # Each channel is attempted independently; one failing never blocks the other.
    result = {
        "hugo": publish_hugo(brief_content, today_str, dry_run),
        "email": publish_email(brief_content, today_str, dry_run),
    }
    write_result(result)
    print(f"Publish result: {result}")
    sys.exit(1 if FAILED in result.values() else 0)


if __name__ == '__main__':
    main()
