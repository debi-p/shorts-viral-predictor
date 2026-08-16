document.getElementById('open-analyzer').addEventListener('click', () => {
  chrome.tabs.create({ url: chrome.runtime.getURL('analyzer.html') });
});
