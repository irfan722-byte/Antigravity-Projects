# 20 Repository structure

```
aurumguard/
  README.md · docker-compose.yml · .gitignore
  backend/
    app/
      config.py · main.py · seed.py
      config/{scoring_config,risk_defaults,strategy_registry}.json
      core/  candles integrity indicators structure regime evidence gates risk contract_spec
             calibration news_state setup decision timeutil  strategies/{base,common,pullback_continuation,breakout_retest,range_rejection,post_news_confirmation}
      paper/engine.py · backtest/{engine,metrics,validation}.py
      providers/{base,registry,twelvedata}.py · providers/mock/{synth,market,calendar,macro}.py
      notifications/{service,webpush}.py
      services/{snapshot,analysis,paper_service,strategy_service,notifications_glue,auth,audit,bus,limiter}.py
      api/{deps,schemas}.py · api/routers/{auth,users,market,decisions,risk,paper,strategies,misc}.py
      db/{base,models}.py
    alembic/ (env.py, versions/a55d681388ec_initial_schema.py) · alembic.ini · ruff.toml
    tests/ (test_core_basics, test_structure_regime_scoring, test_risk, test_news_state, test_decision_engine, test_paper_engine, test_backtest, test_api)
    requirements.txt · requirements-dev.txt · Dockerfile · .env.example
  frontend/
    src/app/ (welcome, login, register, onboarding, (app)/… 22 pages) · src/components/{Providers,AppShell,ui,CandleChart}.tsx
    src/lib/{api,auth,format,i18n,push,types}.ts · src/sw.ts · public/manifest.webmanifest · public/icons
    e2e/smoke.spec.ts · vitest.config.ts · playwright.config.ts · next.config.ts · Dockerfile · .env.example
  docs/ (this set, 01–36)
  infra/terraform/main.tf
.github/workflows/aurumguard-ci.yml
```
