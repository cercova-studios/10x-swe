# Historical GitHub CLI examples

Preserved from the installed January 2026 guide targeting gh 2.85.0. These examples are unverified snapshots, not current CLI contracts. Check the installed command’s `--help` before using a flag. Never print tokens, stage unrelated files, bypass checks, or perform bulk/destructive writes merely because an example shows how.

## Prerequisites

### Installation

```bash
# macOS
brew install gh

# Linux
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt update
sudo apt install gh

# Windows
winget install --id GitHub.cli

# Verify installation
gh --version
```

### Authentication

```bash
# Interactive login (default: github.com)
gh auth login

# Login with specific hostname
gh auth login --hostname enterprise.internal

# Login with token
gh auth login --with-token < mytoken.txt

# Check authentication status
gh auth status

# Switch accounts
gh auth switch --hostname github.com --user username

# Logout
gh auth logout --hostname github.com --user username
```

### Setup Git Integration

```bash
# Configure git to use gh as credential helper
gh auth setup-git

# View active token
gh auth token

# Refresh authentication scopes
gh auth refresh --scopes write:org,read:public_key
```

## CLI Structure

```
gh                          # Root command
├── auth                    # Authentication
│   ├── login
│   ├── logout
│   ├── refresh
│   ├── setup-git
│   ├── status
│   ├── switch
│   └── token
├── browse                  # Open in browser
├── codespace               # GitHub Codespaces
│   ├── code
│   ├── cp
│   ├── create
│   ├── delete
│   ├── edit
│   ├── jupyter
│   ├── list
│   ├── logs
│   ├── ports
│   ├── rebuild
│   ├── ssh
│   ├── stop
│   └── view
├── gist                    # Gists
│   ├── clone
│   ├── create
│   ├── delete
│   ├── edit
│   ├── list
│   ├── rename
│   └── view
├── issue                   # Issues
│   ├── create
│   ├── list
│   ├── status
│   ├── close
│   ├── comment
│   ├── delete
│   ├── develop
│   ├── edit
│   ├── lock
│   ├── pin
│   ├── reopen
│   ├── transfer
│   ├── unlock
│   └── view
├── org                     # Organizations
│   └── list
├── pr                      # Pull Requests
│   ├── create
│   ├── list
│   ├── status
│   ├── checkout
│   ├── checks
│   ├── close
│   ├── comment
│   ├── diff
│   ├── edit
│   ├── lock
│   ├── merge
│   ├── ready
│   ├── reopen
│   ├── revert
│   ├── review
│   ├── unlock
│   ├── update-branch
│   └── view
├── project                 # Projects
│   ├── close
│   ├── copy
│   ├── create
│   ├── delete
│   ├── edit
│   ├── field-create
│   ├── field-delete
│   ├── field-list
│   ├── item-add
│   ├── item-archive
│   ├── item-create
│   ├── item-delete
│   ├── item-edit
│   ├── item-list
│   ├── link
│   ├── list
│   ├── mark-template
│   ├── unlink
│   └── view
├── release                 # Releases
│   ├── create
│   ├── list
│   ├── delete
│   ├── delete-asset
│   ├── download
│   ├── edit
│   ├── upload
│   ├── verify
│   ├── verify-asset
│   └── view
├── repo                    # Repositories
│   ├── create
│   ├── list
│   ├── archive
│   ├── autolink
│   ├── clone
│   ├── delete
│   ├── deploy-key
│   ├── edit
│   ├── fork
│   ├── gitignore
│   ├── license
│   ├── rename
│   ├── set-default
│   ├── sync
│   ├── unarchive
│   └── view
├── cache                   # Actions caches
│   ├── delete
│   └── list
├── run                     # Workflow runs
│   ├── cancel
│   ├── delete
│   ├── download
│   ├── list
│   ├── rerun
│   ├── view
│   └── watch
├── workflow                # Workflows
│   ├── disable
│   ├── enable
│   ├── list
│   ├── run
│   └── view
├── agent-task              # Agent tasks
├── alias                   # Command aliases
│   ├── delete
│   ├── import
│   ├── list
│   └── set
├── api                     # API requests
├── attestation             # Artifact attestations
│   ├── download
│   ├── trusted-root
│   └── verify
├── completion              # Shell completion
├── config                  # Configuration
│   ├── clear-cache
│   ├── get
│   ├── list
│   └── set
├── extension               # Extensions
│   ├── browse
│   ├── create
│   ├── exec
│   ├── install
│   ├── list
│   ├── remove
│   ├── search
│   └── upgrade
├── gpg-key                 # GPG keys
│   ├── add
│   ├── delete
│   └── list
├── label                   # Labels
│   ├── clone
│   ├── create
│   ├── delete
│   ├── edit
│   └── list
├── preview                 # Preview features
├── ruleset                 # Rulesets
│   ├── check
│   ├── list
│   └── view
├── search                  # Search
│   ├── code
│   ├── commits
│   ├── issues
│   ├── prs
│   └── repos
├── secret                  # Secrets
│   ├── delete
│   ├── list
│   └── set
├── ssh-key                 # SSH keys
│   ├── add
│   ├── delete
│   └── list
├── status                  # Status overview
└── variable                # Variables
    ├── delete
    ├── get
    ├── list
    └── set
```

## Configuration

### Global Configuration

```bash
# List all configuration
gh config list

# Get specific configuration value
gh config list git_protocol
gh config get editor

# Set configuration value
gh config set editor vim
gh config set git_protocol ssh
gh config set prompt disabled
gh config set pager "less -R"

# Clear configuration cache
gh config clear-cache
```

### Environment Variables

```bash
# GitHub token (for automation)
export GH_TOKEN=ghp_xxxxxxxxxxxx

# GitHub hostname
export GH_HOST=github.com

# Disable prompts
export GH_PROMPT_DISABLED=true

# Custom editor
export GH_EDITOR=vim

# Custom pager
export GH_PAGER=less

# HTTP timeout
export GH_TIMEOUT=30

# Custom repository (override default)
export GH_REPO=owner/repo

# Custom git protocol
export GH_ENTERPRISE_HOSTNAME=hostname
```

## Authentication (gh auth)

### Login

```bash
# Interactive login
gh auth login

# Web-based authentication
gh auth login --web

# With clipboard for OAuth code
gh auth login --web --clipboard

# With specific git protocol
gh auth login --git-protocol ssh

# With custom hostname (GitHub Enterprise)
gh auth login --hostname enterprise.internal

# Login with token from stdin
gh auth login --with-token < token.txt

# Insecure storage (plain text)
gh auth login --insecure-storage
```

### Status

```bash
# Show all authentication status
gh auth status

# Show active account only
gh auth status --active

# Show specific hostname
gh auth status --hostname github.com

# Show token in output
gh auth status --show-token

# JSON output
gh auth status --json hosts

# Filter with jq
gh auth status --json hosts --jq '.hosts | add'
```

### Switch Accounts

```bash
# Interactive switch
gh auth switch

# Switch to specific user/host
gh auth switch --hostname github.com --user monalisa
```

### Token

```bash
# Print authentication token
gh auth token

# Token for specific host/user
gh auth token --hostname github.com --user monalisa
```

### Refresh

```bash
# Refresh credentials
gh auth refresh

# Add scopes
gh auth refresh --scopes write:org,read:public_key

# Remove scopes
gh auth refresh --remove-scopes delete_repo

# Reset to default scopes
gh auth refresh --reset-scopes

# With clipboard
gh auth refresh --clipboard
```

### Setup Git

```bash
# Setup git credential helper
gh auth setup-git

# Setup for specific host
gh auth setup-git --hostname enterprise.internal

# Force setup even if host not known
gh auth setup-git --hostname enterprise.internal --force
```

## Configuration (gh config)

```bash
# List all config
gh config list

# Get specific value
gh config get editor

# Set value
gh config set editor vim

# Set git protocol
gh config set git_protocol ssh

# Clear cache
gh config clear-cache

# Set prompt behavior
gh config set prompt disabled
gh config set prompt enabled
```

## Environment Setup

### Shell Integration

```bash
# Add to ~/.bashrc or ~/.zshrc
eval "$(gh completion -s bash)"  # or zsh/fish

# Create useful aliases
alias gs='gh status'
alias gpr='gh pr view --web'
alias gir='gh issue view --web'
alias gco='gh pr checkout'
```

### Git Configuration

```bash
# Use gh as credential helper
gh auth setup-git

# Set gh as default for repo operations
git config --global credential.helper 'gh !gh auth setup-git'

# Or manually
git config --global credential.helper github
```
