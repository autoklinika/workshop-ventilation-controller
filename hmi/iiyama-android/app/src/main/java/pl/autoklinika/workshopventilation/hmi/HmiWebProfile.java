package pl.autoklinika.workshopventilation.hmi;

import android.webkit.WebView;

import org.json.JSONObject;

final class HmiWebProfile {

    private static final String STYLE_ID = "wvc-iiyama-hmi-profile";

    private static final String CSS =
            "html,body{overscroll-behavior:none!important;}"
                    + "body{-webkit-overflow-scrolling:auto;}"
                    + "*::-webkit-scrollbar{width:0!important;height:0!important;}"
                    + "@media (min-width:1200px) and (max-width:1320px) and (min-height:720px) and (max-height:840px){"
                    + ".v2-main{margin-left:96px!important;padding:12px 14px 12px!important;}"
                    + ".v2-page-heading{margin:0 0 8px 10px!important;}"
                    + ".v2-page-heading h1{font-size:1.08rem!important;}"
                    + ".v2-page-heading p{margin-top:2px!important;font-size:.74rem!important;}"
                    + ".v2-top-grid{gap:10px!important;}"
                    + ".v2-zone-card,.v2-unit-card,.v2-weather-card{min-height:352px!important;}"
                    + ".v2-zone-header{min-height:76px!important;padding:10px 16px!important;}"
                    + ".v2-zone-header h2{font-size:1.22rem!important;}"
                    + ".v2-zone-icon{width:48px!important;height:48px!important;font-size:1.7rem!important;}"
                    + ".v2-zone-air{min-height:102px!important;padding:10px 18px!important;}"
                    + ".v2-air-status strong{margin-top:5px!important;font-size:1.4rem!important;}"
                    + ".v2-air-value strong{font-size:1.35rem!important;}"
                    + ".v2-zone-control{min-height:170px!important;padding:14px 22px 12px!important;}"
                    + ".v2-control-icon{width:48px!important;height:48px!important;font-size:1.8rem!important;}"
                    + ".v2-control-main{grid-template-columns:50px 1fr!important;gap:10px!important;}"
                    + ".v2-control-main strong{font-size:1.65rem!important;}"
                    + ".v2-control-values{gap:7px!important;padding-left:16px!important;}"
                    + ".v2-bar{height:16px!important;margin-top:6px!important;}"
                    + ".v2-unit-card{padding:12px 20px 14px!important;}"
                    + ".v2-unit-illustration{height:100px!important;margin:0!important;}"
                    + ".v2-unit-box{transform:perspective(600px) rotateX(7deg) scale(.88)!important;}"
                    + ".v2-unit-list{gap:5px!important;margin-top:2px!important;}"
                    + ".v2-unit-list dt,.v2-unit-list dd{font-size:.72rem!important;}"
                    + ".v2-lower-grid{gap:10px!important;margin-top:10px!important;}"
                    + ".v2-panel{min-height:270px!important;padding:12px 18px!important;}"
                    + ".v2-panel>header{gap:10px!important;}"
                    + ".v2-chart-placeholder{height:205px!important;margin-top:8px!important;}"
                    + ".v2-events-list{margin-top:10px!important;gap:8px!important;}"
                    + ".v2-event{min-height:52px!important;padding-bottom:8px!important;}"
                    + ".v2-event-icon{width:36px!important;height:36px!important;}"
                    + "}";

    private HmiWebProfile() {
    }

    static void apply(WebView webView) {
        String quotedCss = JSONObject.quote(CSS);
        String quotedId = JSONObject.quote(STYLE_ID);

        String javascript =
                "(function(){"
                        + "var id=" + quotedId + ";"
                        + "var s=document.getElementById(id);"
                        + "if(!s){s=document.createElement('style');s.id=id;document.head.appendChild(s);}"
                        + "s.textContent=" + quotedCss + ";"
                        + "document.documentElement.classList.add('wvc-iiyama-hmi');"
                        + "})();";

        webView.evaluateJavascript(javascript, null);
    }
}
