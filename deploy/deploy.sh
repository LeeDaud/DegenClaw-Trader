#!/bin/bash
set -e

DOMAIN="degen.licheng.website"
BACKEND_DIR="/opt/degenclaw"
FRONTEND_DIR="/var/www/$DOMAIN"
BACKEND_USER="degenclaw"

echo "=== 1. 创建目录结构 ==="
mkdir -p "$BACKEND_DIR/data"
mkdir -p "$BACKEND_DIR/logs"
mkdir -p "$FRONTEND_DIR"

echo "=== 2. 创建系统用户 ==="
id -u "$BACKEND_USER" &>/dev/null || useradd -r -s /bin/false -d "$BACKEND_DIR" "$BACKEND_USER"

echo "=== 3. 安装系统依赖 ==="
if ! command -v python3 &>/dev/null; then
    apt-get update -qq && apt-get install -y -qq python3 python3-pip python3-venv nginx certbot python3-certbot-nginx
fi

echo "=== 4. 设置 Python 虚拟环境 ==="
python3 -m venv "$BACKEND_DIR/.venv"
source "$BACKEND_DIR/.venv/bin/activate"
pip install -q --upgrade pip
pip install -q -r "$BACKEND_DIR/requirements.txt"

echo "=== 5. 设置 Nginx ==="
cp "/root/deploy/nginx.$DOMAIN.conf" "/etc/nginx/sites-enabled/$DOMAIN.conf"
nginx -t && systemctl reload nginx

echo "=== 6. 获取 SSL 证书 ==="
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email admin@licheng.website || true

echo "=== 7. 创建 systemd 服务 ==="
cat > /etc/systemd/system/degenclaw.service << 'SERVICE'
[Unit]
Description=DegenClaw Alpha Engine
After=network.target

[Service]
Type=simple
User=degenclaw
Group=degenclaw
WorkingDirectory=/opt/degenclaw
EnvironmentFile=/opt/degenclaw/.env
ExecStart=/opt/degenclaw/.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=10
StandardOutput=append:/opt/degenclaw/logs/app.log
StandardError=append:/opt/degenclaw/logs/app.log

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable degenclaw

echo "=== 8. 设置权限 ==="
chown -R "$BACKEND_USER:$BACKEND_USER" "$BACKEND_DIR"
chown -R www-data:www-data "$FRONTEND_DIR"

echo "=== 9. 启动服务 ==="
systemctl start degenclaw
sleep 3
systemctl reload nginx

echo "=== 10. 验证 ==="
sleep 2
echo "--- Backend health ---"
curl -s http://127.0.0.1:8000/api/v1/health || echo "FAILED"
echo ""
echo "--- Frontend ---"
curl -s -o /dev/null -w "HTTP %{http_code}" "https://$DOMAIN/" || echo "FAILED"
echo ""
echo "--- API proxy ---"
curl -s -o /dev/null -w "HTTP %{http_code}" "https://$DOMAIN/api/v1/health" || echo "FAILED"
echo ""
echo "=== 部署完成 ==="
