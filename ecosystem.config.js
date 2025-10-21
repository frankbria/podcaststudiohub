module.exports = {
  apps: [
    {
      name: 'podcaststudiohub-api',
      cwd: '/var/www/podcaststudiohub/api',
      script: '.venv/bin/python3',
      args: '-m uvicorn src.main:app --host 0.0.0.0 --port 8001 --workers 4',
      env: {
        NODE_ENV: 'production'
      },
      error_file: '/var/log/podcaststudiohub/api-error.log',
      out_file: '/var/log/podcaststudiohub/api-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z'
    },
    {
      name: 'podcaststudiohub-celery',
      cwd: '/var/www/podcaststudiohub/api',
      script: '.venv/bin/python3',
      args: '-m celery -A src.tasks.celery_app worker --loglevel=info',
      env: {
        NODE_ENV: 'production'
      },
      error_file: '/var/log/podcaststudiohub/celery-error.log',
      out_file: '/var/log/podcaststudiohub/celery-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z'
    },
    {
      name: 'podcaststudiohub-frontend',
      cwd: '/var/www/podcaststudiohub/frontend',
      script: 'npm',
      args: 'start',
      env: {
        NODE_ENV: 'production',
        PORT: 3001
      },
      error_file: '/var/log/podcaststudiohub/frontend-error.log',
      out_file: '/var/log/podcaststudiohub/frontend-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z'
    }
  ]
};
