// Simple ESM wrapper for tweetnacl-js for Chrome Extension
// This is a minimal implementation that provides Ed25519 signature verification

const nacl = {
  sign: {
    detached: {
      verify: async function(message, signature, publicKey) {
        try {
          // Use Web Crypto API for Ed25519 verification
          const key = await crypto.subtle.importKey(
            'raw',
            publicKey,
            {
              name: 'Ed25519',
              namedCurve: 'Ed25519'
            },
            false,
            ['verify']
          );

          const isValid = await crypto.subtle.verify(
            'Ed25519',
            key,
            signature,
            message
          );

          return isValid;
        } catch (error) {
          console.error('Ed25519 verification failed:', error);
          return false;
        }
      }
    }
  }
};

export default nacl;
export { nacl as sign };