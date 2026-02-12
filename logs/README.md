# Log Files

This folder contains application log files. These files are **not tracked by git** (.gitignore).

## Log Files

- **apply_log.txt** - Price plan application logs
- **competitors_debug.log** - Competitor scraping debug logs
- **server.log** - Main server logs
- **server_log_fresh.txt** - Fresh server session logs

## Log Management

Logs are automatically rotated and managed by the application. Old logs are archived or deleted based on retention policies.

To clear logs:
```bash
rm -f logs/*.log logs/*.txt
```

**Note:** Some scripts write logs directly to the root directory. Consider running them from the project root to maintain log organization.
