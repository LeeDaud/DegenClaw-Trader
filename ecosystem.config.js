// DegenClaw Alpha Engine - PM2 Ecosystem
module.exports = {
  apps: [
    {
      name: 'degenclaw-api',
      cwd: './backend',
      script: 'uvicorn',
      args: 'main:app --host 0.0.0.0 --port 8000',
      interpreter: 'python',
      env: {
        PYTHONPATH: '.',
      },
      watch: false,
      max_restarts: 10,
      restart_delay: 5000,
      exp_backoff_restart_delay: 100,
    },
  ],
}
