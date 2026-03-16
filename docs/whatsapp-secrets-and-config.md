# WhatsApp Secrets and Config

## Required Config Fields

### Connector Configuration

```json
{
  "whatsapp": {
    "enabled": false,
    "webhook_url": "https://your-domain.com/whatsapp/webhook",
    "verify_token": "your_verify_token",
    "access_token": "your_access_token",
    "authorized_senders": ["+1234567890"],
    "rate_limit_per_sender": 5,
    "dedup_window_seconds": 300
  }
}
```

### Environment Variables (Recommended)

```bash
export WHATSAPP_ACCESS_TOKEN="EAA..."
export WHATSAPP_VERIFY_TOKEN="your_verify_token"
```

## Secrets Storage Expectations

### Local Development

- **Config File**: Place real tokens in local `config.json` (not committed)
- **Environment**: Use shell environment variables
- **Permissions**: Restrict file permissions (`chmod 600 config.json`)

### Production Considerations

- **Secret Manager**: Use system keychain or external service
- **Rotation**: Plan for token rotation procedures
- **Access Control**: Limit who can view/modify secrets

## Example-Only Placeholders in Repo

The repository contains only example placeholders:

```json
{
  "whatsapp": {
    "access_token": "EAAEXAMPLE...",
    "verify_token": "example_verify_token"
  }
}
```

**Never commit real secrets to the repository.**

## What Must Never Be Committed

### Forbidden in Git

- Real WhatsApp access tokens
- API keys or secrets
- Private keys
- Database passwords
- Webhook URLs with credentials

### Detection

Pre-commit hooks should reject commits containing:

- `EAA` followed by base64-like strings
- `whatsapp.com` URLs with tokens
- Known secret patterns

## Local Operator Setup Rules

### 1. Create Local Config

```bash
cp config.example.json config.json
# Edit config.json with real values
```

### 2. Set Permissions

```bash
chmod 600 config.json
```

### 3. Test Configuration

```bash
python3 cli.py whatsapp-validate
```

### 4. Environment Variables (Alternative)

```bash
export WHATSAPP_ACCESS_TOKEN="real_token_here"
export WHATSAPP_VERIFY_TOKEN="real_verify_token"
```

### 5. Webhook Setup

- Configure WhatsApp Business API webhook URL
- Set verify token to match config
- Test webhook with `whatsapp-simulate`

## Security Checklist

- [ ] Real tokens not in repository
- [ ] Config file permissions restricted
- [ ] Environment variables used where possible
- [ ] Webhook URL secured (HTTPS)
- [ ] Token rotation procedure documented
- [ ] Access to secrets limited to operators</content>
<parameter name="filePath">/Users/arnesetkewitz/Workspace/HYBRIS/repos/hybris-host/docs/whatsapp-secrets-and-config.md