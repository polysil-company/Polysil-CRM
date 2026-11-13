package com.polysil.crm;

import android.os.Bundle;
import android.webkit.WebView;

import androidx.activity.OnBackPressedCallback;

import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeActivity;
import com.polysil.crm.tracking.TrackingPlugin;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        // TRK-008 · our own plugin lives in the app, so it is registered here, before the bridge starts.
        registerPlugin(TrackingPlugin.class);
        super.onCreate(savedInstanceState);
        getOnBackPressedDispatcher().addCallback(this, new WebViewBackCallback());
    }

    /**
     * TRK-008 · The phone's back button (or back gesture) goes to the previous screen of the web
     * app, the way a browser's back does, and leaves the app only when there is none.
     *
     * Capacitor handles back only through its App plugin, which this app doesn't use, so without
     * this Android closed the app on the first press. The web app's screens are entries in the web
     * view's history (Next.js pushes each navigation), so going back there returns to the screen
     * before. A callback on the dispatcher, rather than onBackPressed, also works with the
     * predictive back gesture that Android 16 turns on for apps targeting it.
     */
    private final class WebViewBackCallback extends OnBackPressedCallback {
        WebViewBackCallback() {
            super(true);
        }

        @Override
        public void handleOnBackPressed() {
            Bridge bridge = getBridge();
            WebView webView = bridge == null ? null : bridge.getWebView();
            if (webView != null && webView.canGoBack()) {
                webView.goBack();
                return;
            }
            // Nothing to go back to: let Android do what it does on a first screen.
            setEnabled(false);
            getOnBackPressedDispatcher().onBackPressed();
            setEnabled(true);
        }
    }
}
