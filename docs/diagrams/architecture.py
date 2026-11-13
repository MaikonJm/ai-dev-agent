"""Architecture diagram with the official AWS icons, laid out by hand.

Every icon and arrow has a fixed position, so the picture stays readable
and can be animated frame by frame (see animate.py).

    pip install diagrams playwright      # icons come from the diagrams package
    python docs/diagrams/architecture.py # writes docs/images/architecture.png

Needs Chrome or Chromium (CHROME=/path/to/chrome to override).
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

import diagrams

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "images"
ICONS = Path(os.path.realpath(Path(diagrams.__file__).parent.parent / "resources"))
CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")

W, H = 2400, 1500

COLORS = {
    "request": "#2563EB",
    "queue": "#EA580C",
    "alert": "#DC2626",
    "ai": "#7C3AED",
    "ops": "#64748B",
}
LEGEND = [
    ("request", "Event / webhook"),
    ("queue", "Queue"),
    ("ai", "Agent and model"),
    ("alert", "Observability"),
    ("ops", "Delivery and secrets"),
]

# name: (icon, x, y, label, sub-label)  -- x, y = icon centre
NODES = {
    "engineer": ("aws/general/user.png", 170, 300, "Engineer", "label · /approve · review"),
    "issue": ("onprem/vcs/github.png", 170, 580, "Issue", "agent-sandbox-shop"),
    "pr": ("onprem/vcs/github.png", 170, 880, "Pull request", "human merges"),
    "actions": ("onprem/ci/github-actions.png", 170, 1300, "GitHub Actions", "tests · image · plan"),
    "apigw": ("aws/network/api-gateway.png", 520, 380, "API Gateway", "HTTP API"),
    "webhook": ("aws/compute/lambda.png", 800, 380, "Webhook Lambda", "HMAC · allowlist · dedup"),
    "sqs": ("aws/integration/simple-queue-service-sqs.png", 1080, 380, "SQS jobs", "+ dead letter queue"),
    "dispatcher": ("aws/compute/lambda.png", 1360, 380, "Dispatcher Lambda", "ECS RunTask"),
    "ddb": ("aws/database/dynamodb.png", 1880, 380, "DynamoDB", "task state"),
    "fargate": ("aws/compute/fargate.png", 1060, 860, "Agent runner", "plan or implement"),
    "bedrock": ("aws/ml/bedrock.png", 1810, 760, "Amazon Bedrock", "Claude Haiku · Sonnet"),
    "params": ("aws/management/systems-manager-parameter-store.png", 1810, 990, "Parameter Store",
               "App key · webhook secret"),
    "role": ("aws/security/identity-and-access-management-iam-role.png", 520, 1300, "CI role", "GitHub OIDC"),
    "ecr": ("aws/compute/ec2-container-registry.png", 760, 1300, "Amazon ECR", "runner image"),
    "cw": ("aws/management/cloudwatch.png", 1060, 1300, "CloudWatch", "logs · metrics · dashboard"),
    "sns": ("aws/integration/simple-notification-service-sns.png", 1300, 1300, "Amazon SNS", "alarm e-mails"),
    "xray": ("aws/devtools/x-ray.png", 1560, 1300, "AWS X-Ray", "Lambda traces"),
    "s3": ("aws/storage/simple-storage-service-s3.png", 1810, 1300, "S3 state", "Terraform, native lock"),
}

# (x0, y0, x1, y1, title, border, fill, title colour, group icon, title on the right)
BOXES = [
    (40, 215, 300, 1000, "GitHub", "#24292F", "#F6F8FA", "#24292F", None, False),
    (360, 160, 2050, 1450, "AWS Cloud · us-east-1", "#232F3E", "#FFFFFF", "#232F3E", "aws/aws.png", False),
    (390, 205, 2020, 520, "Event-driven pipeline · zero idle cost", "#E7157B", "#FDF2F8", "#BE185D", None, False),
    (390, 560, 1540, 1160, "VPC 10.30.0.0/16 · public subnets · no NAT gateway", "#8C4FFF", "#FAF7FF", "#6B2BD9",
     "aws/network/vpc.png", False),
    (600, 640, 1500, 1110, "Fargate sandbox · one task per job · HTTPS egress only", "#ED7100", "#FFF8F1",
     "#B85700", "aws/compute/fargate.png", False),
    (1570, 560, 2020, 1160, "Model and secrets", "#01A88D", "#EEFBF8", "#047A66", None, False),
    (390, 1200, 2020, 1420, "Delivery and observability", "#7AA116", "#F5FAEE", "#4D6B0A", None, False),
]

# (id, kind, points, label, label_at, dashed)
EDGES = [
    ("engineer-issue", "request", [(170, 392), (170, 532)], "label agent", (170, 462), False),
    ("issue-apigw", "request", [(215, 580), (330, 580), (330, 380), (475, 380)], "webhook", (330, 480), False),
    ("apigw-webhook", "request", [(565, 380), (755, 380)], "", None, False),
    ("webhook-sqs", "queue", [(845, 380), (1035, 380)], "job", None, False),
    ("webhook-ddb", "ops", [(800, 335), (800, 268), (1880, 268), (1880, 335)], "state", (1340, 268), True),
    ("sqs-dispatcher", "queue", [(1125, 380), (1315, 380)], "consume", None, False),
    ("dispatcher-fargate", "queue", [(1360, 475), (1360, 700), (1060, 700), (1060, 815)], "RunTask", (1210, 700),
     False),
    ("fargate-bedrock", "ai", [(1105, 840), (1600, 840), (1600, 760), (1765, 760)], "plan · write · test",
     (1350, 840), False),
    ("fargate-params", "ops", [(1105, 890), (1640, 890), (1640, 990), (1765, 990)], "App key", (1350, 890), True),
    ("fargate-pr", "ai", [(1015, 880), (215, 880)], "comment plan · push branch · open PR", (600, 880), False),
    ("pr-engineer", "ops", [(125, 880), (70, 880), (70, 300), (125, 300)], "", None, False),
    ("actions-role", "ops", [(215, 1300), (475, 1300)], "OIDC", None, False),
    ("role-ecr", "ops", [(565, 1300), (715, 1300)], "push", None, False),
    ("ecr-sandbox", "ops", [(760, 1255), (760, 1112)], "pull", (760, 1185), True),
    ("fargate-cw", "alert", [(1060, 955), (1060, 1255)], "logs · EMF metrics", (1060, 1135), True),
    ("cw-sns", "alert", [(1105, 1300), (1255, 1300)], "alarms", None, False),
]


def icon_uri(rel: str) -> str:
    data = base64.b64encode((ICONS / rel).read_bytes()).decode()
    return f"data:image/png;base64,{data}"


def label_point(points, at):
    if at:
        return at
    best = max(zip(points, points[1:]), key=lambda s: abs(s[1][0] - s[0][0]) + abs(s[1][1] - s[0][1]))
    (x0, y0), (x1, y1) = best
    return ((x0 + x1) / 2, (y0 + y1) / 2)


def render_html(highlight: set[str] | None = None, active_nodes: set[str] | None = None,
                caption: str = "") -> str:
    """highlight: edge ids to emphasise (others dimmed); None = normal picture."""
    dim = highlight is not None
    parts = [f"""<!doctype html><html><head><meta charset="utf-8"><style>
    *{{box-sizing:border-box}} body{{margin:0;width:{W}px;height:{H}px;background:#fff;
      font-family:Inter,'Helvetica Neue',Arial,sans-serif;position:relative;overflow:hidden}}
    .box{{position:absolute;border:2.5px solid;border-radius:18px}}
    .box .t{{position:absolute;left:16px;top:10px;font-weight:700;font-size:21px;letter-spacing:.2px}}
    .n{{position:absolute;width:210px;margin-left:-105px;text-align:center;transition:opacity .2s}}
    .n img{{width:84px;height:84px;object-fit:contain;display:block;margin:0 auto 6px}}
    .n .l{{font-weight:700;font-size:20px;color:#0F172A;line-height:1.15}}
    .n .s{{font-weight:500;font-size:16px;color:#475569;line-height:1.2}}
    .el{{position:absolute;transform:translate(-50%,-50%);background:#fff;border:2px solid;border-radius:999px;
        padding:3px 12px;font-weight:700;font-size:16px;white-space:nowrap}}
    .dim{{opacity:.18}}
    </style></head><body>"""]

    parts.append(f"""<div style="position:absolute;left:40px;top:34px">
      <div style="font-size:46px;font-weight:800;color:#0F172A;letter-spacing:-.5px">AI Dev Agent</div>
      <div style="font-size:22px;font-weight:500;color:#475569;margin-top:6px">
      GitHub issue → approved plan → code and tests in a Fargate sandbox → pull request · serverless · 100% Terraform</div></div>""")
    legend = "".join(
        f'<span style="display:inline-flex;align-items:center;margin-left:26px;font-size:18px;font-weight:600;color:#334155">'
        f'<span style="width:34px;height:5px;border-radius:3px;background:{COLORS[k]};margin-right:9px"></span>{t}</span>'
        for k, t in LEGEND)
    parts.append(f'<div style="position:absolute;right:40px;top:58px">{legend}</div>')

    for x0, y0, x1, y1, title, border, fill, tcol, gicon, right in BOXES:
        img = (f'<img src="{icon_uri(gicon)}" style="width:30px;height:30px;object-fit:contain;'
               f'vertical-align:middle;margin-right:9px;margin-top:-3px">') if gicon else ""
        side = "right:16px;left:auto" if right else ""
        parts.append(f'<div class="box" style="left:{x0}px;top:{y0}px;width:{x1-x0}px;height:{y1-y0}px;'
                     f'border-color:{border};background:{fill}"><div class="t" style="color:{tcol};{side}">{img}{title}</div></div>')

    # arrows
    svg = [f'<svg width="{W}" height="{H}" style="position:absolute;left:0;top:0" xmlns="http://www.w3.org/2000/svg"><defs>']
    for k, c in COLORS.items():
        svg.append(f'<marker id="a-{k}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" '
                   f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>')
    svg.append("</defs>")
    labels = []
    for eid, kind, pts, label, at, dashed in EDGES:
        on = not dim or eid in highlight
        width = 6 if (dim and on) else 3.5
        opacity = 1 if on else 0.15
        d = "M" + " L".join(f"{x},{y}" for x, y in pts)
        dash = ' stroke-dasharray="10 8"' if dashed else ""
        svg.append(f'<path d="{d}" fill="none" stroke="{COLORS[kind]}" stroke-width="{width}" stroke-linejoin="round"'
                   f'{dash} opacity="{opacity}" marker-end="url(#a-{kind})"/>')
        if label:
            x, y = label_point(pts, at)
            labels.append(f'<div class="el" style="left:{x}px;top:{y}px;color:{COLORS[kind]};border-color:{COLORS[kind]};'
                          f'opacity:{opacity}">{label}</div>')
    svg.append("</svg>")
    parts.extend(svg)
    parts.extend(labels)

    for name, (icon, x, y, label, sub) in NODES.items():
        cls = "n" + (" dim" if dim and active_nodes is not None and name not in active_nodes else "")
        sub_html = f'<div class="s">{sub}</div>' if sub else ""
        parts.append(f'<div class="{cls}" style="left:{x}px;top:{y-42}px"><img src="{icon_uri(icon)}">'
                     f'<div class="l">{label}</div>{sub_html}</div>')

    if caption:
        parts.append(f'<div style="position:absolute;left:50%;bottom:22px;transform:translateX(-50%);background:#0F172A;'
                     f'color:#fff;font-size:26px;font-weight:700;padding:12px 28px;border-radius:14px">{caption}</div>')
    parts.append("</body></html>")
    return "".join(parts)


def screenshot(pages: list[tuple[str, Path]], scale: float = 2) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME)
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=scale)
        for html, path in pages:
            page.set_content(html)
            page.wait_for_timeout(150)
            page.screenshot(path=str(path))
        browser.close()


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    screenshot([(render_html(), OUT / "architecture.png")])
    print("wrote", OUT / "architecture.png")
