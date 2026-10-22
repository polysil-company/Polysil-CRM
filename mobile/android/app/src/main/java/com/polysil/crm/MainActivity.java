package com.polysil.crm;

import android.os.Bundle;

import com.getcapacitor.BridgeActivity;
import com.polysil.crm.tracking.TrackingPlugin;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        // TRK-008 · our own plugin lives in the app, so it is registered here, before the bridge starts.
        registerPlugin(TrackingPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
