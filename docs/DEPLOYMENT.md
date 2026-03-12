# miniClaw Deployment Guide

## Overview

miniClaw supports two deployment modes:
1. **Docker Deployment** - Containerized deployment for easy setup and production use
2. **Local Development** - Direct installation for development and debugging

---

## Prerequisites

### Docker Deployment
- Docker 20.10+
- Docker Compose 2.0+

### Local Development
- Python 3.10+
- Node.js 18+
- npm or yarn

---

## Environment Variables

Create a `.env` file in the project root:

```bash
# LLM Configuration
LLM_PROVIDER=qwen  # Options: openai, deepseek, qwen, ollama

# OpenAI (if using OpenAI)
OPENAI_API_KEY=sk-xxx
OPENAI_MODEL=gpt-4o-mini

# DeepSeek (if using DeepSeek)
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_MODEL=deepseek-chat

# Qwen (通义千问) - Default for testing
QWEN_API_KEY=sk-xxx
QWEN_MODEL=qwen-plus

# Ollama (if using local Ollama)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen:7b

# Backend Configuration
BACKEND_PORT=8002
BACKEND_HOST=0.0.0.0
WORKSPACE_PATH=./data/workspace
KNOWLEDGE_BASE_PATH=./data/knowledge_base
SESSIONS_PATH=./data/sessions

# Frontend Configuration
NEXT_PUBLIC_API_URL=http://localhost:8002
```

---

## Docker Deployment (Recommended)

### Quick Start

1. **Clone the repository:**

```bash
git clone <repository-url>
cd miniclaw
```

2. **Configure environment:**

```bash
cp .env.example .env
# Edit .env with your API keys
```

3. **Start the system:**

```bash
docker-compose up -d
```

4. **Access the application:**

- Frontend: http://localhost:3000
- Backend API: http://localhost:8002
- API Docs: http://localhost:8002/docs

### Docker Compose Services

The `docker-compose.yml` includes:

- **backend**: Python FastAPI service
  - Port: 8002
  - Volume mounts: ./data, ./backend/app

- **frontend**: Next.js frontend service
  - Port: 3000
  - Volume mounts: ./frontend

### Docker Commands

```bash
# Start all services
docker-compose up -d

# Start specific service
docker-compose up backend

# View logs
docker-compose logs -f

# View logs for specific service
docker-compose logs -f backend

# Stop all services
docker-compose down

# Stop and remove volumes
docker-compose down -v

# Rebuild services
docker-compose up -d --build

# Scale services
docker-compose up -d --scale backend=2
```

### Production Deployment

For production, update `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  backend:
    image: mini-openclaw-backend:latest
    restart: always
    environment:
      - ENVIRONMENT=production
    ports:
      - "8002:8002"

  frontend:
    image: mini-openclaw-frontend:latest
    restart: always
    ports:
      - "80:3000"
```

```bash
docker-compose -f docker-compose.prod.yml up -d
```

---

## Local Development Deployment

### Backend Setup

1. **Install Python dependencies:**

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Configure environment:**

```bash
cp .env.example .env
# Edit .env with your configuration
```

3. **Run the backend:**

```bash
# Development mode with auto-reload
uvicorn app.main:app --port 8002 --reload

# Production mode
uvicorn app.main:app --port 8002 --host 0.0.0.0 --workers 4
```

### Frontend Setup

1. **Install Node dependencies:**

```bash
cd frontend
npm install
```

2. **Configure environment:**

```bash
cp .env.example .env.local
# Edit .env.local with your configuration
```

3. **Run the frontend:**

```bash
# Development mode
npm run dev

# Production build
npm run build
npm start
```

### Development Workflow

Run both backend and frontend in separate terminals:

```bash
# Terminal 1: Backend
cd backend
uvicorn app.main:app --port 8002 --reload

# Terminal 2: Frontend
cd frontend
npm run dev
```

---

## Verification

### Check Backend Health

```bash
curl http://localhost:8002/health
```

Expected response:

```json
{
  "status": "healthy",
  "version": "0.1.0"
}
```

### Test Chat Endpoint

```bash
curl -N http://localhost:8002/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "Hello!"}
    ]
  }'
```

### Check Frontend

Visit http://localhost:3000 in your browser.

---

## Troubleshooting

### Backend Issues

**Port already in use:**

```bash
# Find process using port 8002
lsof -i :8002  # Linux/Mac
netstat -ano | findstr :8002  # Windows

# Kill process
kill -9 <PID>  # Linux/Mac
taskkill /PID <PID> /F  # Windows
```

**Import errors:**

```bash
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

### Frontend Issues

**Build errors:**

```bash
# Clear cache and rebuild
rm -rf .next node_modules
npm install
npm run dev
```

**API connection issues:**

- Verify `NEXT_PUBLIC_API_URL` in `.env.local`
- Check if backend is running: `curl http://localhost:8002/health`
- Check browser console for CORS errors

### Docker Issues

**Container won't start:**

```bash
# View logs
docker-compose logs backend

# Rebuild container
docker-compose up -d --build

# Remove all containers and volumes
docker-compose down -v
docker-compose up -d --build
```

**Volume permission issues:**

```bash
# Fix permissions on Linux
sudo chown -R $USER:$USER ./data
```

---

## Performance Tuning

### Backend Optimization

1. **Increase worker count:**

```bash
uvicorn app.main:app --workers 4 --port 8002
```

2. **Enable caching:**

Edit `backend/app/config.py`:

```python
ENABLE_CACHE = True
CACHE_TTL = 3600  # 1 hour
```

3. **Database optimization:** (if using a database)

```bash
# Run migrations
python -m alembic upgrade head
```

### Frontend Optimization

1. **Enable production build:**

```bash
npm run build
```

2. **Configure CDN:** Update `next.config.js`

```javascript
module.exports = {
  assetPrefix: 'https://cdn.example.com',
}
```

---

## Security Considerations

### Production Checklist

- [ ] Enable HTTPS/TLS
- [ ] Implement API authentication
- [ ] Set up CORS properly
- [ ] Configure rate limiting
- [ ] Enable request logging
- [ ] Set up monitoring and alerts
- [ ] Regular security updates
- [ ] Backup strategy for data

### SSL/TLS Setup

Using nginx as reverse proxy:

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location /api/ {
        proxy_pass http://localhost:8002;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

---

## Monitoring

### Backend Logs

```bash
# Docker
docker-compose logs -f backend

# Local
tail -f backend/logs/app.log
```

### Frontend Logs

Check browser console for client-side errors.

### Health Monitoring

Set up automated health checks:

```bash
# Add to crontab
*/5 * * * * curl -f http://localhost:8002/health || alert-admin
```

---

## Backup and Restore

### Data Backup

```bash
# Backup data directory
tar -czf backup-$(date +%Y%m%d).tar.gz ./data

# Restore
tar -xzf backup-20240101.tar.gz
```

### Database Backup (if using)

```bash
# PostgreSQL
pg_dump miniclaw > backup.sql

# Restore
psql miniclaw < backup.sql
```

---

## Scaling

### Horizontal Scaling

```yaml
# docker-compose.scale.yml
version: '3.8'

services:
  backend:
    deploy:
      replicas: 3

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
```

### Load Balancing

Use nginx or HAProxy to distribute load:

```nginx
upstream backend {
    server backend1:8002;
    server backend2:8002;
    server backend3:8002;
}

server {
    location /api/ {
        proxy_pass http://backend;
    }
}
```

---

## Updates and Maintenance

### Updating the Application

```bash
# Pull latest code
git pull origin main

# Rebuild and restart
docker-compose down
docker-compose up -d --build
```

### Database Migrations

```bash
# Backend
cd backend
python -m alembic upgrade head
```

---

## Support

For issues and questions:
- GitHub Issues: [repository-url]/issues
- Documentation: [repository-url]/wiki
- Email: support@example.com
