/* Preview-only switch: URL ?business_os=1. Does not alter application state. */
(function(){try{if(new URLSearchParams(location.search).get("business_os")==="1")
 document.body.classList.add("business-os");}catch(_err){}})();