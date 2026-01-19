Multi-Factor Authentication (MFA)
=================================

Inmor supports Multi-Factor Authentication (MFA) to add an extra layer of
security to administrator accounts. MFA is powered by django-allauth and
supports multiple authentication methods.

.. contents:: On this page
   :local:
   :depth: 2

Overview
--------

MFA provides additional security beyond username and password by requiring
a second factor for authentication. Inmor supports:

* **TOTP (Time-based One-Time Password)** - Use authenticator apps like
  Google Authenticator, Authy, or 1Password
* **WebAuthn/Security Keys** - Use hardware security keys like YubiKey or
  built-in platform authenticators (Touch ID, Windows Hello)

Accessing MFA Settings
----------------------

After logging in, administrators can access MFA settings at:

``/accounts/2fa/``

Or through the Django admin interface by clicking the "MFA Settings" link.

.. figure:: /_static/screenshots/mfa-02-index.png
   :alt: MFA Settings Page
   :width: 100%

   Two-Factor Authentication settings page

Setting Up TOTP
---------------

TOTP (Time-based One-Time Password) uses authenticator apps to generate
6-digit codes that change every 30 seconds.

1. Navigate to MFA Settings (``/accounts/2fa/``)
2. Click **Activate** under "Authenticator App"
3. Scan the QR code with your authenticator app
4. Enter the 6-digit verification code from your app
5. Click **Activate** to complete setup

.. figure:: /_static/screenshots/mfa-03-totp-activate.png
   :alt: TOTP Activation Page
   :width: 100%

   TOTP activation with QR code and secret key

.. tip::

   Save the **Secret Key** shown below the QR code. You can use this to
   manually add the account to your authenticator app if QR scanning
   doesn't work.

Recommended Authenticator Apps
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

* **Google Authenticator** (iOS, Android)
* **Authy** (iOS, Android, Desktop) - Supports cloud backup
* **1Password** (iOS, Android, Desktop) - Integrated with password manager
* **Microsoft Authenticator** (iOS, Android)

Setting Up Security Keys
------------------------

WebAuthn security keys provide phishing-resistant authentication using
hardware tokens or built-in platform authenticators.

1. Navigate to MFA Settings (``/accounts/2fa/``)
2. Click **Add** under "Security Keys"
3. Follow your browser's prompts to register your security key
4. Give the key a memorable name

.. figure:: /_static/screenshots/mfa-04-webauthn.png
   :alt: Security Keys Page
   :width: 100%

   Security Keys management page

Supported Security Keys
^^^^^^^^^^^^^^^^^^^^^^^

* **YubiKey** (USB-A, USB-C, NFC)
* **Google Titan** (USB, Bluetooth)
* **Feitian** keys
* **Platform authenticators**:

  - Touch ID (macOS)
  - Face ID (iOS)
  - Windows Hello (Windows)
  - Fingerprint sensors (Android)

Recovery Codes
--------------

When you activate MFA, recovery codes are generated as a backup method.
These codes can be used if you lose access to your authenticator app or
security key.

.. warning::

   Store recovery codes in a secure location separate from your password.
   Each code can only be used once.

To view or regenerate recovery codes:

1. Navigate to MFA Settings
2. Click on "Recovery Codes"
3. Download or copy the codes to a secure location

Logging In with MFA
-------------------

After MFA is enabled:

1. Enter your username and password as usual
2. You will be prompted for your second factor
3. Either:

   - Enter the 6-digit code from your authenticator app, or
   - Insert and activate your security key

Re-authentication
-----------------

For sensitive operations (like changing MFA settings), you may be asked
to re-authenticate by entering your password again. This provides
additional security for administrative actions.

Disabling MFA
-------------

To disable an MFA method:

1. Navigate to MFA Settings
2. Click **Deactivate** next to the method you want to disable

.. danger::

   Disabling all MFA methods removes the extra security layer from your
   account. Consider keeping at least one MFA method active for
   administrative accounts.

Configuration
-------------

MFA is enabled by default in Inmor. To configure MFA settings, update
your Django settings:

.. code-block:: python

   # Enable/disable MFA methods
   MFA_SUPPORTED_TYPES = ["totp", "webauthn", "recovery_codes"]

   # Require re-authentication for sensitive operations
   MFA_PASSKEY_LOGIN_ENABLED = True

   # WebAuthn relying party settings
   MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN = False  # Set True for localhost dev

For production deployments, ensure your site is served over HTTPS as
WebAuthn requires a secure context.

Troubleshooting
---------------

**QR code not scanning**
   Try manually entering the secret key shown below the QR code into
   your authenticator app.

**Security key not detected**
   Ensure your browser supports WebAuthn (Chrome, Firefox, Safari, Edge).
   Check that the key is properly inserted or NFC is enabled.

**Lost authenticator/security key**
   Use a recovery code to log in, then set up a new authentication method.

**Time sync issues with TOTP**
   Ensure your device's clock is synchronized. TOTP codes are time-sensitive
   and require accurate time.
