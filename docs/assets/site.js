
document.addEventListener('DOMContentLoaded',function(){
  // ---- master table: sort (desktop rows + mobile cards in lockstep) ----
  var deskBody=document.querySelector('#m-desk tbody');
  var cardWrap=document.querySelector('#m-cards');
  var sortState={key:null,dir:-1};
  function reorder(key){
    if(sortState.key===key){sortState.dir=-sortState.dir;}else{sortState.key=key;sortState.dir=-1;}
    var dir=sortState.dir;
    function val(el){var v=parseFloat(el.getAttribute('data-'+key));return isNaN(v)?-1:v;}
    if(deskBody){
      Array.from(deskBody.querySelectorAll('tr'))
        .sort(function(a,b){return (val(a)-val(b))*dir;})
        .forEach(function(r){deskBody.appendChild(r);});
    }
    if(cardWrap){
      Array.from(cardWrap.querySelectorAll('.mcard'))
        .sort(function(a,b){return (val(a)-val(b))*dir;})
        .forEach(function(r){cardWrap.appendChild(r);});
    }
    document.querySelectorAll('#m-desk th.sortable').forEach(function(th){
      th.classList.toggle('active', th.dataset.sort===key);
    });
  }
  document.querySelectorAll('#m-desk th.sortable').forEach(function(th){
    th.addEventListener('click',function(){reorder(th.dataset.sort);});
  });
  // ---- class filter chips (hide/show rows + cards) ----
  var active={};
  document.querySelectorAll('.chip[data-c]').forEach(function(c){active[c.dataset.c]=true;});
  function applyFilter(){
    document.querySelectorAll('#m-desk tbody tr, #m-cards .mcard').forEach(function(el){
      el.style.display = active[el.dataset.cls]===false ? 'none' : '';
    });
  }
  document.querySelectorAll('.chip[data-c]').forEach(function(c){
    c.addEventListener('click',function(){
      active[c.dataset.c]=!active[c.dataset.c];
      c.classList.toggle('off',!active[c.dataset.c]);
      applyFilter();
    });
  });
});
