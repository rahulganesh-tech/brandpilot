/**
 * BrandPilot for Google Docs (early version).
 * Checks the selected text (or the whole document) with the BrandPilot API and
 * shows each issue in a sidebar, with its reason, source and one-click fix.
 */

var PROPS = PropertiesService.getUserProperties();

function onOpen() {
  DocumentApp.getUi()
    .createMenu('BrandPilot')
    .addItem('Check selection or document', 'showSidebar')
    .addItem('Settings', 'showSettings')
    .addToUi();
}

function onInstall() {
  onOpen();
}

function showSidebar() {
  var html = HtmlService.createHtmlOutputFromFile('Sidebar').setTitle('BrandPilot');
  DocumentApp.getUi().showSidebar(html);
}

function showSettings() {
  var ui = DocumentApp.getUi();
  var current = PROPS.getProperty('API_URL') || '';
  var res = ui.prompt(
    'BrandPilot settings',
    'API URL (your brandpilot-api Cloud Run URL)' + (current ? '\nNow: ' + current : ''),
    ui.ButtonSet.OK_CANCEL
  );
  if (res.getSelectedButton() !== ui.Button.OK) return;
  var url = res.getResponseText().trim().replace(/\/+$/, '');
  if (!/^https:\/\/[^\s]+\.run\.app$/.test(url)) {
    ui.alert('Please enter the https://….run.app URL of the BrandPilot API.');
    return;
  }
  PROPS.setProperty('API_URL', url);
  PROPS.deleteProperty('BRAND_ID');
  ui.alert('Saved. Open BrandPilot → Check selection or document.');
}

function api_(method, path, body) {
  var base = PROPS.getProperty('API_URL');
  if (!base) throw new Error('Set the API URL first: BrandPilot → Settings.');
  var options = { method: method, contentType: 'application/json', muteHttpExceptions: true };
  if (body !== undefined) options.payload = JSON.stringify(body);
  var res = UrlFetchApp.fetch(base + path, options);
  var code = res.getResponseCode();
  var data = res.getContentText() ? JSON.parse(res.getContentText()) : null;
  if (code >= 400) throw new Error((data && typeof data.detail === 'string') ? data.detail : 'BrandPilot error ' + code);
  return data;
}

function brandId_() {
  var id = PROPS.getProperty('BRAND_ID');
  if (id) return id;
  var brands = api_('get', '/brands');
  if (!brands || !brands.length) throw new Error('No brand found. Add one in the BrandPilot Brand vault.');
  PROPS.setProperty('BRAND_ID', brands[0].id);
  return brands[0].id;
}

function selectedText_() {
  var doc = DocumentApp.getActiveDocument();
  var sel = doc.getSelection();
  if (sel) {
    var parts = [];
    sel.getRangeElements().forEach(function (r) {
      var el = r.getElement();
      if (!el.editAsText) return;
      var text = el.asText().getText();
      parts.push(r.isPartial() ? text.substring(r.getStartOffset(), r.getEndOffsetInclusive() + 1) : text);
    });
    var joined = parts.join('\n').trim();
    if (joined) return { text: joined, scope: 'selection' };
  }
  return { text: doc.getBody().getText().trim(), scope: 'document' };
}

/** Called from the sidebar. */
function checkDocument() {
  var input = selectedText_();
  if (!input.text) throw new Error('The document is empty.');
  if (input.text.length > 20000) throw new Error('Select a shorter part (20,000 characters at most).');
  var bundle = api_('post', '/scans', {
    brand_id: brandId_(),
    content: input.text,
    channel: 'document',
    author: 'Docs user'
  });
  highlight_(bundle.issues);
  return {
    scope: input.scope,
    scanId: bundle.scan.id,
    aiStatus: bundle.scan.ai_status,
    issues: bundle.issues.filter(function (i) { return i.decision === 'open'; })
  };
}

function escapeRe_(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function highlight_(issues) {
  var body = DocumentApp.getActiveDocument().getBody();
  issues.forEach(function (i) {
    if (i.decision !== 'open' || i.span_start < 0) return;
    var found = body.findText(escapeRe_(i.excerpt));
    if (found) {
      found.getElement().asText().setBackgroundColor(found.getStartOffset(), found.getEndOffsetInclusive(),
        i.severity === 'high' ? '#FAD2DE' : '#FFF1C2');
    }
  });
}

/** Accept a suggested fix: change the document and record the decision in BrandPilot. */
function acceptFix(issueId, excerpt, fix) {
  var body = DocumentApp.getActiveDocument().getBody();
  var found = body.findText(escapeRe_(excerpt));
  if (!found) throw new Error('Could not find “' + excerpt + '” in the document any more.');
  var text = found.getElement().asText();
  var start = found.getStartOffset();
  var end = found.getEndOffsetInclusive();
  text.setBackgroundColor(start, end, null);
  text.deleteText(start, end);
  if (fix) text.insertText(start, fix);
  api_('patch', '/issues/' + issueId, { decision: 'accepted', author: 'Docs user' });
  return true;
}

function ignoreIssue(issueId, reason) {
  api_('patch', '/issues/' + issueId, { decision: 'ignored', reason: reason, author: 'Docs user' });
  return true;
}
