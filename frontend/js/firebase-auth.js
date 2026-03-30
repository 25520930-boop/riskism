window.FirebaseAuthBridge = {
    enabled: false,
    initialized: false,
    auth: null,
    provider: null,

    init(config) {
        if (this.initialized) return this.enabled;
        this.initialized = true;

        if (!config || typeof window.firebase === 'undefined') {
            return false;
        }

        try {
            if (!window.firebase.apps.length) {
                window.firebase.initializeApp(config);
            }
            this.auth = window.firebase.auth();
            this.provider = new window.firebase.auth.GoogleAuthProvider();
            this.provider.setCustomParameters({ prompt: 'select_account' });
            this.enabled = true;
        } catch (err) {
            console.warn('[Firebase] Init failed:', err);
            this.enabled = false;
        }

        return this.enabled;
    },

    async signInWithGoogle() {
        if (!this.enabled || !this.auth || !this.provider) {
            throw new Error('Firebase Auth is not enabled');
        }

        const result = await this.auth.signInWithPopup(this.provider);
        const user = result?.user;
        if (!user) {
            throw new Error('Missing Firebase user profile');
        }

        return {
            idToken: await user.getIdToken(),
            email: user.email || '',
            displayName: user.displayName || '',
            photoURL: user.photoURL || '',
        };
    },

    async signOut() {
        if (!this.auth) return;
        try {
            await this.auth.signOut();
        } catch (err) {
            console.warn('[Firebase] Sign out failed:', err);
        }
    },
};
