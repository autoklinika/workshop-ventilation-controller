package pl.autoklinika.workshopventilation.hmi;

import android.webkit.WebView;

import org.json.JSONObject;

final class HmiWebProfile {

    private static final String STYLE_ID = "wvc-iiyama-hmi-profile";

    private static final String CSS =
            "html,body{overscroll-behavior:none!important;}"
                    + "html{font-size:17px!important;-webkit-text-size-adjust:100%;text-size-adjust:100%;}"
                    + "body{-webkit-overflow-scrolling:auto;}"
                    + "*::-webkit-scrollbar{width:0!important;height:0!important;}"
                    + "button,input,select,textarea{touch-action:manipulation;}"
                    + "@media (min-width:1200px) and (max-width:1320px) and (min-height:720px) and (max-height:840px){"
                    + ".v2-body{min-width:0!important;overflow-x:hidden!important;}"
                    + ".v2-sidebar{width:108px!important;padding:12px 9px 16px!important;}"
                    + ".v2-main{margin-left:108px!important;padding:14px 16px 18px!important;min-height:100vh!important;}"
                    + ".v2-nav{min-height:90px!important;gap:7px!important;margin-bottom:4px!important;font-size:.78rem!important;}"
                    + ".v2-nav-icon{width:44px!important;height:44px!important;}"
                    + ".v2-nav-icon svg{width:31px!important;height:31px!important;}"
                    + ".v2-page-heading{margin:0 0 12px 8px!important;}"
                    + ".v2-page-heading h1{font-size:1.32rem!important;}"
                    + ".v2-page-heading p{margin-top:4px!important;font-size:.84rem!important;}"
                    + ".v2-top-grid{grid-template-columns:minmax(0,1.05fr) minmax(0,1.02fr) minmax(270px,.8fr)!important;gap:12px!important;}"
                    + ".v2-zone-card,.v2-unit-card,.v2-weather-card{min-height:370px!important;}"
                    + ".v2-zone-header{min-height:82px!important;padding:12px 17px!important;}"
                    + ".v2-zone-header h2{font-size:1.34rem!important;}"
                    + ".v2-zone-header span{font-size:.82rem!important;}"
                    + ".v2-zone-icon{width:52px!important;height:52px!important;font-size:1.8rem!important;}"
                    + ".v2-zone-air{min-height:110px!important;padding:12px 18px!important;}"
                    + ".v2-air-status span,.v2-air-value span,.v2-control-main span,.v2-control-values span{font-size:.82rem!important;}"
                    + ".v2-air-status strong{margin-top:6px!important;font-size:1.48rem!important;}"
                    + ".v2-air-value strong{font-size:1.45rem!important;}"
                    + ".v2-zone-control{min-height:176px!important;padding:15px 22px 14px!important;}"
                    + ".v2-control-icon{width:52px!important;height:52px!important;font-size:1.9rem!important;}"
                    + ".v2-control-main{grid-template-columns:54px 1fr!important;gap:11px!important;}"
                    + ".v2-control-main strong{font-size:1.72rem!important;}"
                    + ".v2-control-main small{font-size:.8rem!important;}"
                    + ".v2-control-values{gap:8px!important;padding-left:17px!important;}"
                    + ".v2-bar{height:17px!important;margin-top:7px!important;}"
                    + ".v2-unit-card{padding:15px 20px 16px!important;}"
                    + ".v2-unit-kicker{font-size:.76rem!important;}"
                    + ".v2-unit-card h2{font-size:1.38rem!important;}"
                    + ".v2-unit-illustration{height:106px!important;margin:0!important;}"
                    + ".v2-unit-box{transform:perspective(600px) rotateX(7deg) scale(.9)!important;}"
                    + ".v2-unit-list{gap:6px!important;margin-top:3px!important;}"
                    + ".v2-unit-list dt,.v2-unit-list dd{font-size:.76rem!important;}"
                    + ".v2-lower-grid{gap:12px!important;margin-top:12px!important;}"
                    + ".v2-panel{min-height:278px!important;padding:14px 18px!important;}"
                    + ".v2-panel h3{font-size:1.02rem!important;}"
                    + ".v2-chart-placeholder{height:210px!important;margin-top:9px!important;}"
                    + ".v2-events-list{margin-top:10px!important;gap:8px!important;}"
                    + ".v2-event{min-height:54px!important;padding-bottom:8px!important;}"
                    + ".v2-event strong{font-size:.82rem!important;}"
                    + ".v2-event small{font-size:.75rem!important;}"
                    + ".schedule-main{padding-bottom:24px!important;}"
                    + ".schedule-overview{gap:10px!important;margin-bottom:12px!important;}"
                    + ".schedule-overview article{padding:14px 16px!important;}"
                    + ".schedule-overview span,.schedule-zone-state span,.schedule-kicker,.schedule-columns{font-size:12px!important;}"
                    + ".schedule-overview strong{font-size:19px!important;}"
                    + ".schedule-overview small{font-size:12px!important;}"
                    + ".schedule-note{padding:13px 16px!important;margin-bottom:13px!important;font-size:14px!important;}"
                    + ".schedule-grid{gap:13px!important;}"
                    + ".schedule-zone{padding:16px!important;}"
                    + ".schedule-zone>header{padding-bottom:12px!important;}"
                    + ".schedule-zone h2{font-size:20px!important;}"
                    + ".schedule-columns{padding:12px 8px 7px!important;}"
                    + ".schedule-row{padding:7px!important;}"
                    + ".schedule-row input,.schedule-row select{min-height:44px!important;padding:10px!important;font-size:14px!important;}"
                    + ".schedule-zone footer{margin-top:12px!important;padding-top:12px!important;}"
                    + ".schedule-btn{min-height:46px!important;padding:9px 14px!important;font-size:14px!important;}"
                    + ".zigbee-settings-layout{grid-template-columns:205px minmax(0,1fr)!important;gap:13px!important;}"
                    + ".zigbee-settings-menu{top:14px!important;padding:12px!important;}"
                    + ".zigbee-settings-menu-item{padding:12px 10px!important;}"
                    + ".zigbee-settings-menu-item strong{font-size:.92rem!important;}"
                    + ".zigbee-settings-menu-item small{font-size:.74rem!important;}"
                    + ".zigbee-settings-readonly{font-size:.68rem!important;}"
                    + ".zigbee-settings-content{gap:12px!important;}"
                    + ".zigbee-settings-header,.zigbee-management-panel{gap:14px!important;padding:16px!important;}"
                    + ".zigbee-settings-header h2{font-size:1.36rem!important;}"
                    + ".zigbee-management-panel h3{font-size:1.12rem!important;}"
                    + ".zigbee-settings-header p,.zigbee-management-panel p{font-size:.84rem!important;}"
                    + ".zigbee-summary{gap:10px!important;}"
                    + ".zigbee-summary article{padding:14px 15px!important;}"
                    + ".zigbee-summary span{font-size:.7rem!important;}"
                    + ".zigbee-summary strong{font-size:1.55rem!important;}"
                    + ".zigbee-summary small{font-size:.74rem!important;}"
                    + ".zigbee-action,.zigbee-remove{min-height:46px!important;padding:0 14px!important;font-size:.78rem!important;}"
                    + ".zigbee-inventory-card{padding:14px 15px!important;gap:12px!important;}"
                    + ".zigbee-inventory-main p,.zigbee-inventory-meta{font-size:.76rem!important;}"
                    + ".zigbee-device-management label{font-size:.7rem!important;}"
                    + ".zigbee-rename-input,.zigbee-role-select{height:46px!important;font-size:.82rem!important;}"
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
