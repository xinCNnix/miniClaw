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

Create a `.env` file in the backend directory:

```bash
# LLM Configuration
LLM_PROVIDER=  # Options: openai, deepseek, qwen, ollama, claude, gemini

# OpenAI (if using OpenAI)
OPENAI_API_KEY=sk-xxx
OPENAI_MODEL=

# DeepSeek (if using DeepSeek)
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_MODEL=

# Qwen (Alibaba Qwen) - Default for testing
QWEN_API_KEY=sk-xxx
QWEN_MODEL=

# Ollama (if using local Ollama)
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=

# Claude (if using Claude)
CLAUDE_API_KEY=sk-ant-xxx
CLAUDE_MODEL=

# Gemini (if using Gemini)
GEMINI_API_KEY=xxx
GEMINI_MODEL=

# Backend Configuration
BACKEND_PORT=8002
BACKEND_HOST=0.0.0.0
WORKSPACE_PATH=./workspace
KNOWLEDGE_BASE_PATH=./data/knowledge_base
SESSIONS_PATH=./data/sessions
SKILLS_DIR=./data/skills
VECTOR_STORE_DIR=./data/vector_store

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
cp backend/.env.example backend/.env
# Edit backend/.env with your API keys
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
  - Volume mounts: ./backend, ./data
  - Environment: Loads from backend/.env

- **frontend**: Next.js frontend service
  - Port: 3000
  - Depends on: backend
  - Environment: NEXT_PUBLIC_API_URL

### Docker Commands

```bash
# Start all services
docker-compose up -d

# Start in background with logs
docker-compose up -d --build

# View logs
docker-compose logs -f

# View logs for specific service
docker-compose logs -f backend
docker-compose logs -f frontend

# Stop services
docker-compose down

# Stop and remove volumes
docker-compose down -v

# Rebuild services
docker-compose up -d --build

# Execute command in backend container
docker-compose exec backend bash

# Execute command in frontend container
docker-compose exec frontend sh
```

### Production Docker Deployment

For production deployment, consider:

1. **Use environment-specific `.env` files**

```bash
# Production .env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-prod-xxx
OPENAI_MODEL=gpt-4o-mini
```

2. **Configure proper CORS**

Edit `backend/app/main.py`:

```python
CORS_ORIGINS = [
    "https://your-domain.com",
    "https://www.your-domain.com"
]
```

3. **Enable HTTPS**

Use a reverse proxy (nginx/traefik) with SSL certificates.

4. **Set resource limits**

```yaml
# docker-compose.prod.yml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '1.0'
          memory: 1G
```

---

## Local Development Deployment

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Start development server
uvicorn app.main:app --port 8002 --reload
```

Backend will be available at http://localhost:8002

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Configure environment
echo "NEXT_PUBLIC_API_URL=http://localhost:8002" > .env.local

# Start development server
npm run dev
```

Frontend will be available at http://localhost:3000

### Using Startup Scripts

**Windows:**
```bash
# Double-click start.bat
# Or run from command line
start.bat
```

**Linux/macOS:**
```bash
chmod +x start.sh
./start.sh
```

These scripts will:
1. Check and install dependencies
2. Start backend (port 8002)
3. Wait for backend to be ready
4. Start frontend (port 3000)
5. Open browser automatically

---

## Production Deployment

### Backend Production Server

Using **Gunicorn** with Uvicorn workers:

```bash
cd backend

# Install gunicorn
pip install gunicorn

# Start production server
gunicorn app.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8002 \
  --access-logfile - \
  --error-logfile - \
  --log-level info
```

### Frontend Production Build

```bash
cd frontend

# Build for production
npm run build

# Start production server
npm start
```

Or use a Node.js process manager like **PM2**:

```bash
# Install PM2
npm install -g pm2

# Start backend
cd backend
pm2 start "uvicorn app.main:app --port 8002" --name miniclaw-backend

# Start frontend
cd frontend
pm2 start "npm start" --name miniclaw-frontend

# Save PM2 configuration
pm2 save

# Setup PM2 to start on system boot
pm2 startup
```

### Nginx Reverse Proxy Configuration

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL certificates
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # Frontend
    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # Backend API
    location /api/ {
        proxy_pass http://localhost:8002;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;

        # SSE support
        proxy_buffering off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    # API docs
    location /docs {
        proxy_pass http://localhost:8002;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }
}
```

---

## Cloud Deployment

### Deploy to VPS (DigitalOcean, AWS, GCP)

1. **Provision server** (Ubuntu 20.04+ recommended)

2. **Install Docker and Docker Compose**

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
sudo usermod -aG docker $USER
```

3. **Clone repository**

```bash
git clone <repository-url>
cd miniclaw
```

4. **Configure environment**

```bash
cp backend/.env.example backend/.env
nano backend/.env  # Edit with your API keys
```

5. **Start services**

```bash
docker-compose up -d
```

6. **Configure reverse proxy** (nginx + Let's Encrypt)

```bash
# Install nginx and certbot
sudo apt update
sudo apt install nginx certbot python3-certbot-nginx

# Configure nginx
sudo nano /etc/nginx/sites-available/miniclaw
# Add nginx configuration from above

# Enable site
sudo ln -s /etc/nginx/sites-available/miniclaw /etc/nginx/sites-enabled/

# Obtain SSL certificate
sudo certbot --nginx -d your-domain.com
```

### Deploy to AWS ECS

1. **Create ECR repositories**

```bash
aws ecr create-repository --repository-name miniclaw-backend
aws ecr create-repository --repository-name miniclaw-frontend
```

2. **Build and push Docker images**

```bash
# Backend
docker build -t miniclaw-backend backend
docker tag miniclaw-backend:latest <account-id>.dkr.ecr.<region>.amazonaws.com/miniclaw-backend:latest
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/miniclaw-backend:latest

# Frontend
docker build -t miniclaw-frontend frontend
docker tag miniclaw-frontend:latest <account-id>.dkr.ecr.<region>.amazonaws.com/miniclaw-frontend:latest
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/miniclaw-frontend:latest
```

3. **Create ECS task definition and service**

Use AWS Console or AWS CLI to configure ECS.

---

## Troubleshooting

### Backend Issues

**Problem**: Backend fails to start

**Solution**:
```bash
# Check if port 8002 is already in use
lsof -i :8002  # Linux/macOS
netstat -ano | findstr :8002  # Windows

# Check backend logs
docker-compose logs backend
```

**Problem**: LLM API connection fails

**Solution**:
- Verify API key in `.env` file
- Check network connectivity
- Try testing API key with curl

### Frontend Issues

**Problem**: Frontend cannot connect to backend

**Solution**:
- Ensure backend is running: `curl http://localhost:8002/health`
- Check `NEXT_PUBLIC_API_URL` in frontend `.env.local`
- Verify CORS configuration

**Problem**: Build fails

**Solution**:
```bash
cd frontend
rm -rf .next node_modules
npm install
npm run build
```

### Docker Issues

**Problem**: Containers cannot communicate

**Solution**:
- Ensure both services are in the same Docker network
- Check service names in docker-compose.yml
- Verify no port conflicts

**Problem**: Volume permissions

**Solution**:
```bash
# Fix volume permissions on Linux
sudo chown -R $USER:$USER ./data
```

---

## Health Checks

### Backend Health Check

```bash
# Check if backend is running
curl http://localhost:8002/health

# Expected response
{
  "status": "healthy",
  "version": "0.1.0"
}
```

### Frontend Health Check

```bash
# Check if frontend is running
curl http://localhost:3000

# Or in browser
# Navigate to http://localhost:3000
```

---

## Backup and Restore

### Backup Data

```bash
# Backup all data
tar -czf miniclaw-backup-$(date +%Y%m%d).tar.gz ./data ./backend/.env

# Backup to cloud storage (optional)
aws s3 cp miniclaw-backup-$(date +%Y%m%d).tar.gz s3://your-bucket/
```

### Restore Data

```bash
# Stop services
docker-compose down

# Restore data
tar -xzf miniclaw-backup-20240304.tar.gz

# Start services
docker-compose up -d
```

---

## Monitoring

### Logs

```bash
# View all logs
docker-compose logs -f

# View backend logs
docker-compose logs -f backend

# View logs from last 100 lines
docker-compose logs --tail=100 backend
```

### Metrics (Optional)

Consider setting up monitoring tools:
- **Prometheus + Grafana** for metrics visualization
- **Sentry** for error tracking
- **LangSmith** for LLM tracing (requires LANGCHAIN_API_KEY)

---

## Security Best Practices

1. **Never commit `.env` files** to version control
2. **Use strong API keys** and rotate them regularly
3. **Enable HTTPS** in production
4. **Configure CORS** whitelist properly
5. **Use firewall** to restrict access
6. **Keep dependencies updated**:
   ```bash
   cd backend && pip install --upgrade -r requirements.txt
   cd frontend && npm update
   ```
7. **Regular backups** of data directory
8. **Monitor logs** for suspicious activity

---

## Scaling Considerations

### Backend Scaling

- Use **Gunicorn with multiple workers**
- Deploy behind **load balancer** (nginx/HAProxy)
- Consider **serverless** deployment (AWS Lambda, Google Cloud Run)

### Frontend Scaling

- Use **CDN** for static assets
- Enable **gzip/brotli** compression
- Implement **caching** strategies
- Consider **static export** (`npm run build && npm run export`)

---

## Support

For deployment issues:
- Check logs: `docker-compose logs -f`
- Verify environment variables
- Check network connectivity
- Review documentation in `docs/` directory

---

*Last Updated: 2024-03-14*
