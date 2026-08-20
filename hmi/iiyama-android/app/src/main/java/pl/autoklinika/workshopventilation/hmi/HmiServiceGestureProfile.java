package pl.autoklinika.workshopventilation.hmi;

import android.webkit.WebView;

/** Injects the hidden five-tap service gesture into the local WebGUI surface. */
final class HmiServiceGestureProfile {

    private static final String JAVASCRIPT =
            "(function(){"
                    + "if(window.__wvcServiceGestureInstalled){return;}"
                    + "window.__wvcServiceGestureInstalled=true;"
                    + "var taps=[];"
                    + "document.addEventListener('click',function(event){"
                    + "var target=event.target&&event.target.closest?event.target.closest('.v2-nav[data-route=\"/\"]'):null;"
                    + "if(!target){return;}"
                    + "var dashboard=document.getElementById('dashboardView');"
                    + "var active=(target.classList.contains('active')||target.getAttribute('aria-current')==='page')&&dashboard&&!dashboard.hidden;"
                    + "if(!active){taps=[];return;}"
                    + "var now=Date.now();"
                    + "taps=taps.filter(function(value){return now-value<=4000;});"
                    + "taps.push(now);"
                    + "if(taps.length<5){return;}"
                    + "taps=[];"
                    + "try{"
                    + "if(window.WvcKioskBridge&&window.WvcKioskBridge.requestServicePin){"
                    + "window.WvcKioskBridge.requestServicePin();"
                    + "}"
                    + "}catch(ignore){}"
                    + "},true);"
                    + "})();";

    private HmiServiceGestureProfile() {
    }

    static void apply(WebView webView) {
        webView.evaluateJavascript(JAVASCRIPT, null);
    }
}
