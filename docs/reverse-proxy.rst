Reverse Proxy Configuration
============================

In production deployments, Inmor runs behind a reverse proxy that handles TLS termination.
This is the recommended setup as it:

* Provides TLS/HTTPS encryption for external clients
* Allows the internal services to communicate over HTTP
* Enables load balancing and high availability
* Simplifies certificate management

Architecture
------------

.. code-block:: text

   Internet
       │
       ▼
   ┌────────────────────────────────────────┐
   │           Reverse Proxy                │
   │       (nginx/Apache/Caddy)             │
   │                                        │
   │   *.federation.example.com:443 (TLS)   │
   └────────────────────────────────────────┘
       │                              │
       ▼                              ▼
   ┌──────────────┐          ┌──────────────┐
   │  Trust Anchor │          │ Admin Portal │
   │  :8080 (HTTP) │          │ :8000 (HTTP) │
   └──────────────┘          └──────────────┘

The reverse proxy terminates TLS and forwards requests to the internal HTTP services.

.. _securing-admin-api:

Securing the Admin API
----------------------

.. danger::

   **The Admin API MUST be protected in production.**

   The Admin API provides unrestricted management access to the Trust Anchor.
   An attacker with access could:

   * Issue fraudulent trust marks to malicious entities
   * Revoke legitimate trust marks, disrupting federation operations
   * Add rogue subordinates to the federation
   * Modify or destroy the Trust Anchor configuration

   **At minimum, protect the Admin API with HTTP Basic Authentication.**

Basic Authentication Setup
^^^^^^^^^^^^^^^^^^^^^^^^^^

**nginx**

1. Create a password file::

      sudo apt install apache2-utils  # For htpasswd
      sudo htpasswd -c /etc/nginx/.htpasswd admin

2. Add to your server block::

      auth_basic "Admin API";
      auth_basic_user_file /etc/nginx/.htpasswd;

**Apache (httpd)**

1. Create a password file::

      sudo htpasswd -c /etc/httpd/.htpasswd admin

2. Add to your VirtualHost::

      <Location />
          AuthType Basic
          AuthName "Admin API"
          AuthUserFile /etc/httpd/.htpasswd
          Require valid-user
      </Location>

**Caddy**

Use the ``basicauth`` directive in your Caddyfile::

   admin.federation.example.com {
       basicauth {
           admin $2a$14$... # Use: caddy hash-password
       }
       reverse_proxy localhost:8000
   }

Generate password hash with: ``caddy hash-password``

nginx Configuration
-------------------

Complete Setup
^^^^^^^^^^^^^^

Create ``/etc/nginx/sites-available/inmor.conf``:

.. code-block:: nginx

   # Trust Anchor - Federation endpoints (public)
   server {
       listen 443 ssl http2;
       server_name federation.example.com;

       ssl_certificate /etc/letsencrypt/live/federation.example.com/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/federation.example.com/privkey.pem;

       # Modern TLS configuration
       ssl_protocols TLSv1.2 TLSv1.3;
       ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
       ssl_prefer_server_ciphers off;

       # Security headers
       add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

       # Proxy to Trust Anchor
       location / {
           proxy_pass http://127.0.0.1:8080;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }

   # Admin Portal - Management API (protected)
   server {
       listen 443 ssl http2;
       server_name admin.federation.example.com;

       ssl_certificate /etc/letsencrypt/live/admin.federation.example.com/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/admin.federation.example.com/privkey.pem;

       ssl_protocols TLSv1.2 TLSv1.3;
       ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
       ssl_prefer_server_ciphers off;

       # REQUIRED: Basic authentication
       auth_basic "Admin API";
       auth_basic_user_file /etc/nginx/.htpasswd;

       # Optional: IP allowlist (additional layer)
       # allow 10.0.0.0/8;
       # allow 192.168.0.0/16;
       # deny all;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }

   # Redirect HTTP to HTTPS
   server {
       listen 80;
       server_name federation.example.com admin.federation.example.com;
       return 301 https://$server_name$request_uri;
   }

Enable and test::

   sudo ln -s /etc/nginx/sites-available/inmor.conf /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl reload nginx

Single Domain Setup (nginx)
^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you prefer a single domain with path-based routing:

.. code-block:: nginx

   server {
       listen 443 ssl http2;
       server_name federation.example.com;

       ssl_certificate /etc/letsencrypt/live/federation.example.com/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/federation.example.com/privkey.pem;

       # Trust Anchor endpoints (public)
       location /.well-known/openid-federation {
           proxy_pass http://127.0.0.1:8080;
           proxy_set_header Host $host;
           proxy_set_header X-Forwarded-Proto $scheme;
       }

       location ~ ^/(fetch|list|resolve|trust_mark|trust_mark_list|trust_mark_status|historical_keys|collection)$ {
           proxy_pass http://127.0.0.1:8080;
           proxy_set_header Host $host;
           proxy_set_header X-Forwarded-Proto $scheme;
       }

       # Admin API (protected with basic auth)
       location /api/ {
           auth_basic "Admin API";
           auth_basic_user_file /etc/nginx/.htpasswd;

           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Forwarded-Proto $scheme;
       }

       # Default - Trust Anchor
       location / {
           proxy_pass http://127.0.0.1:8080;
           proxy_set_header Host $host;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }

Rate Limiting (nginx)
^^^^^^^^^^^^^^^^^^^^^

Add rate limiting for public endpoints:

.. code-block:: nginx

   # In http block
   limit_req_zone $binary_remote_addr zone=federation:10m rate=10r/s;

   # In server/location block
   location / {
       limit_req zone=federation burst=20 nodelay;
       proxy_pass http://127.0.0.1:8080;
   }

Apache (httpd) Configuration
-----------------------------

Prerequisites
^^^^^^^^^^^^^

Enable required modules::

   sudo a2enmod proxy proxy_http ssl headers rewrite

Complete Setup
^^^^^^^^^^^^^^

Create ``/etc/apache2/sites-available/inmor.conf`` (Debian/Ubuntu) or
``/etc/httpd/conf.d/inmor.conf`` (RHEL/CentOS):

.. code-block:: apache

   # Trust Anchor - Federation endpoints (public)
   <VirtualHost *:443>
       ServerName federation.example.com

       SSLEngine on
       SSLCertificateFile /etc/letsencrypt/live/federation.example.com/fullchain.pem
       SSLCertificateKeyFile /etc/letsencrypt/live/federation.example.com/privkey.pem

       # Modern TLS configuration
       SSLProtocol all -SSLv3 -TLSv1 -TLSv1.1
       SSLCipherSuite ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256

       # Security headers
       Header always set Strict-Transport-Security "max-age=31536000; includeSubDomains"

       # Proxy to Trust Anchor
       ProxyPreserveHost On
       ProxyPass / http://127.0.0.1:8080/
       ProxyPassReverse / http://127.0.0.1:8080/

       RequestHeader set X-Forwarded-Proto "https"
   </VirtualHost>

   # Admin Portal - Management API (protected)
   <VirtualHost *:443>
       ServerName admin.federation.example.com

       SSLEngine on
       SSLCertificateFile /etc/letsencrypt/live/admin.federation.example.com/fullchain.pem
       SSLCertificateKeyFile /etc/letsencrypt/live/admin.federation.example.com/privkey.pem

       SSLProtocol all -SSLv3 -TLSv1 -TLSv1.1
       SSLCipherSuite ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256

       # Proxy to Admin Portal
       ProxyPreserveHost On
       ProxyPass / http://127.0.0.1:8000/
       ProxyPassReverse / http://127.0.0.1:8000/

       RequestHeader set X-Forwarded-Proto "https"

       # REQUIRED: Basic authentication
       <Location />
           AuthType Basic
           AuthName "Admin API"
           AuthUserFile /etc/httpd/.htpasswd
           Require valid-user
       </Location>

       # Optional: IP allowlist (additional layer)
       # <Location />
       #     Require ip 10.0.0.0/8 192.168.0.0/16
       # </Location>
   </VirtualHost>

   # Redirect HTTP to HTTPS
   <VirtualHost *:80>
       ServerName federation.example.com
       ServerAlias admin.federation.example.com
       Redirect permanent / https://federation.example.com/
   </VirtualHost>

Enable and test::

   # Debian/Ubuntu
   sudo a2ensite inmor.conf
   sudo apache2ctl configtest
   sudo systemctl reload apache2

   # RHEL/CentOS
   sudo httpd -t
   sudo systemctl reload httpd

Single Domain Setup (Apache)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: apache

   <VirtualHost *:443>
       ServerName federation.example.com

       SSLEngine on
       SSLCertificateFile /etc/letsencrypt/live/federation.example.com/fullchain.pem
       SSLCertificateKeyFile /etc/letsencrypt/live/federation.example.com/privkey.pem

       # Trust Anchor endpoints (public)
       ProxyPass /.well-known/openid-federation http://127.0.0.1:8080/.well-known/openid-federation
       ProxyPassReverse /.well-known/openid-federation http://127.0.0.1:8080/.well-known/openid-federation

       ProxyPassMatch ^/(fetch|list|resolve|trust_mark|trust_mark_list|trust_mark_status|historical_keys|collection)$ http://127.0.0.1:8080/$1
       ProxyPassReverse / http://127.0.0.1:8080/

       # Admin API (protected with basic auth)
       <Location /api/>
           AuthType Basic
           AuthName "Admin API"
           AuthUserFile /etc/httpd/.htpasswd
           Require valid-user

           ProxyPass http://127.0.0.1:8000/api/
           ProxyPassReverse http://127.0.0.1:8000/api/
       </Location>

       # Default - Trust Anchor
       ProxyPass / http://127.0.0.1:8080/
       ProxyPassReverse / http://127.0.0.1:8080/

       RequestHeader set X-Forwarded-Proto "https"
   </VirtualHost>

Rate Limiting (Apache)
^^^^^^^^^^^^^^^^^^^^^^

Use mod_ratelimit or mod_qos::

   # Enable module
   sudo a2enmod ratelimit

   # In VirtualHost
   <Location />
       SetOutputFilter RATE_LIMIT
       SetEnv rate-limit 500
   </Location>

Caddy Configuration
-------------------

Caddy provides automatic HTTPS with Let's Encrypt by default.

Complete Setup
^^^^^^^^^^^^^^

Create ``/etc/caddy/Caddyfile``:

.. code-block:: text

   # Trust Anchor - Federation endpoints (public)
   federation.example.com {
       reverse_proxy localhost:8080

       header Strict-Transport-Security "max-age=31536000; includeSubDomains"
   }

   # Admin Portal - Management API (protected)
   admin.federation.example.com {
       # REQUIRED: Basic authentication
       basicauth {
           admin $2a$14$Zkx19XLiW6VYouLHR5NmfOFU0z2GTNmpkT/5qqR7hx4IjWJPDhjvG
       }

       # Optional: IP allowlist (additional layer)
       # @allowed remote_ip 10.0.0.0/8 192.168.0.0/16
       # handle @allowed {
       #     reverse_proxy localhost:8000
       # }
       # respond 403

       reverse_proxy localhost:8000
   }

Generate password hash::

   caddy hash-password

Enable and run::

   sudo systemctl enable caddy
   sudo systemctl start caddy

   # Or reload after config changes
   sudo systemctl reload caddy

Single Domain Setup (Caddy)
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: text

   federation.example.com {
       # Trust Anchor endpoints (public)
       handle /.well-known/openid-federation {
           reverse_proxy localhost:8080
       }

       handle_path /fetch {
           reverse_proxy localhost:8080
       }

       handle_path /list {
           reverse_proxy localhost:8080
       }

       handle_path /resolve {
           reverse_proxy localhost:8080
       }

       handle_path /trust_mark* {
           reverse_proxy localhost:8080
       }

       handle_path /historical_keys {
           reverse_proxy localhost:8080
       }

       # Admin API (protected with basic auth)
       handle /api/* {
           basicauth {
               admin $2a$14$...
           }
           reverse_proxy localhost:8000
       }

       # Default - Trust Anchor
       handle {
           reverse_proxy localhost:8080
       }
   }

Rate Limiting (Caddy)
^^^^^^^^^^^^^^^^^^^^^

Use the rate_limit directive (requires caddy-ratelimit plugin)::

   federation.example.com {
       rate_limit {
           zone dynamic {
               key {remote_host}
               events 10
               window 1s
           }
       }
       reverse_proxy localhost:8080
   }

TLS Certificate Management
--------------------------

Let's Encrypt with Certbot (nginx)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

::

   # Install certbot
   sudo apt install certbot python3-certbot-nginx

   # Obtain certificates
   sudo certbot --nginx -d federation.example.com -d admin.federation.example.com

   # Auto-renewal is configured automatically
   sudo systemctl status certbot.timer

Let's Encrypt with Certbot (Apache)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

::

   # Install certbot
   sudo apt install certbot python3-certbot-apache

   # Obtain certificates
   sudo certbot --apache -d federation.example.com -d admin.federation.example.com

Let's Encrypt with Caddy
^^^^^^^^^^^^^^^^^^^^^^^^

Caddy handles TLS certificates automatically. No additional configuration needed.
Certificates are obtained and renewed automatically when Caddy starts.

Manual Certificate Installation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For manually obtained certificates::

   # Create certificate directory
   sudo mkdir -p /etc/ssl/inmor

   # Copy certificates
   sudo cp fullchain.pem /etc/ssl/inmor/
   sudo cp privkey.pem /etc/ssl/inmor/
   sudo chmod 600 /etc/ssl/inmor/privkey.pem

Security Best Practices
-----------------------

1. **Always Protect Admin API**

   Never expose the Admin API without authentication. Use Basic Auth at minimum,
   consider IP allowlisting or VPN for additional security.

2. **Use Strong TLS Configuration**

   * Disable TLS 1.0 and 1.1
   * Use modern cipher suites
   * Enable HSTS

3. **Enable Logging**

   **nginx**::

      access_log /var/log/nginx/inmor-access.log;
      error_log /var/log/nginx/inmor-error.log;

   **Apache**::

      ErrorLog ${APACHE_LOG_DIR}/inmor-error.log
      CustomLog ${APACHE_LOG_DIR}/inmor-access.log combined

   **Caddy**::

      federation.example.com {
          log {
              output file /var/log/caddy/inmor-access.log
          }
          reverse_proxy localhost:8080
      }

4. **Rate Limiting**

   Implement rate limiting on public endpoints to prevent abuse.

5. **Regular Updates**

   Keep your reverse proxy software updated for security patches.

Updating Django Settings
------------------------

When running behind a reverse proxy, update ``localsettings.py``::

   # Trust the X-Forwarded headers from proxy
   SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
   USE_X_FORWARDED_HOST = True

   # Set the canonical domain
   TA_DOMAIN = 'https://federation.example.com'
   TRUSTMARK_PROVIDER = 'https://federation.example.com'

   # Allow the proxy host
   ALLOWED_HOSTS = ['federation.example.com', 'admin.federation.example.com', 'localhost']

Testing the Setup
-----------------

1. Test the Trust Anchor::

      curl https://federation.example.com/.well-known/openid-federation

2. Test trust chain resolution::

      curl "https://federation.example.com/resolve?sub=https://example-rp.com&trust_anchor=https://federation.example.com"

3. Test Admin API with authentication::

      curl -u admin:password https://admin.federation.example.com/api/v1/trustmarktypes
