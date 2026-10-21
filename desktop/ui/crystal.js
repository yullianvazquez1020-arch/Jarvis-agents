(function(){"use strict";
  var $=function(id){return document.getElementById(id);};
  function mirror(source,target){var update=function(){$(target).textContent=$(source).textContent;};update();new MutationObserver(update).observe($(source),{childList:true,characterData:true,subtree:true});}
  function phase(){document.body.dataset.voice=$("state").textContent.split(" — ")[0];} phase(); new MutationObserver(phase).observe($("state"),{childList:true,characterData:true,subtree:true});
  mirror("state","crystal-state");mirror("state","estado");mirror("reply","crystal-reply");mirror("st-mouse","crystal-mouse");mirror("st-ax","crystal-ax");
  document.querySelectorAll("[data-launch]").forEach(function(b){b.onclick=function(){$("transcript").value=b.getAttribute("data-launch");$("send").click();};});
  $("crystal-business").onclick=function(){if(!document.body.classList.contains("ver-paneles"))$("paneles").click();document.querySelector('[data-panel="brief"]').click();};
})();
