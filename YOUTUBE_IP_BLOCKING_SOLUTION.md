# YouTube IP Blocking Solution for Alibaba Cloud

## Problem Identified

Your VideoCatcher application is experiencing **YouTube IP blocking** on Alibaba Cloud servers. The error "Precondition check failed" indicates that YouTube is blocking requests from your server's IP address (8.216.33.211 - Alibaba Cloud Tokyo).

## Root Cause

- **Local Success**: Your command line works because your local IP is not blocked
- **Docker Failure**: The Alibaba Cloud server IP is blocked by YouTube's anti-bot systems
- **Error Pattern**: "HTTP Error 400: Bad Request" and "Precondition check failed" are typical IP blocking responses

## Solutions (Choose One)

### Solution 1: HTTP/SOCKS Proxy (Recommended)

1. **Get a proxy service** (residential proxies work best):
   - Bright Data, Oxylabs, or similar services
   - Residential proxies from US/EU locations

2. **Configure proxy in docker-compose.yml**:
   ```yaml
   environment:
     - YT_DLP_PROXY=http://username:password@proxy-server:port
     # OR for SOCKS5:
     # - YT_DLP_PROXY=socks5://username:password@proxy-server:port
   ```

3. **Restart the container**:
   ```bash
   docker-compose down
   docker-compose up -d
   ```

### Solution 2: VPN Container (Advanced)

1. **Add VPN container to docker-compose.yml**:
   ```yaml
   services:
     vpn:
       image: dperson/openvpn-client
       cap_add:
         - NET_ADMIN
       devices:
         - /dev/net/tun
       volumes:
         - ./vpn-config:/vpn
       command: '-f "" -r 192.168.1.0/24'
   
     videocatcher:
       depends_on:
         - vpn
       network_mode: "service:vpn"
       # ... rest of your config
   ```

### Solution 3: Server Migration

**Move to a different cloud provider/region**:
- AWS, Google Cloud, or DigitalOcean
- Avoid known blocked IP ranges
- Choose US/EU regions

### Solution 4: IP Rotation Service

**Use rotating proxy services**:
- Configure multiple proxy endpoints
- Implement automatic failover
- Rotate IPs on failure

## Testing Your Solution

1. **Test proxy connectivity**:
   ```bash
   docker exec videocatcher python -c "import requests; print(requests.get('https://ipinfo.io/json', proxies={'http': 'your-proxy', 'https': 'your-proxy'}).json())"
   ```

2. **Test YouTube access**:
   ```bash
   docker exec videocatcher yt-dlp --cookies /app/cookies/cookies.txt --list-formats https://www.youtube.com/watch?v=dQw4w9WgXcQ
   ```

## Quick Fix Implementation

**I've already updated your code to support proxies**:
- Added `YT_DLP_PROXY` environment variable support
- Updated `app.py` to use proxy when configured
- Added proxy configuration examples in `docker-compose.yml`

**To activate**:
1. Get a proxy service
2. Uncomment and configure the proxy line in `docker-compose.yml`
3. Restart: `docker-compose down && docker-compose up -d`

## Why This Happens

- YouTube actively blocks cloud provider IPs
- Alibaba Cloud IPs are commonly blocked
- This affects many automation tools, not just yt-dlp
- The blocking is based on IP reputation and usage patterns

## Cost Considerations

- **Residential Proxies**: $50-200/month for reliable service
- **VPN Services**: $5-20/month but may also get blocked
- **Server Migration**: Similar hosting costs, one-time migration effort

Choose the solution that best fits your budget and technical requirements.