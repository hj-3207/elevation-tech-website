/* Anonymous download-click counters, loaded by the four product pages. Was duplicated
   inline; extracted so the endpoint and key live in one place. apps.html does not need it:
   its buttons link to the product pages rather than to a download or a store.

   Fire-and-forget: this can never block or break the actual download, which
   opens in a new tab. Only a timestamp is stored — no personal data. The
   publishable key is safe to expose, because RLS lets visitors INSERT only,
   never read or edit.

   Each app writes to its own table. `downloads` is Rack Detector's and has no app
   column, so nothing else may share it: doing so would silently fold those clicks into
   the Detector count. Table definitions live in the Detector repo, in
   licensing/supabase_downloads_admin.sql.

   The Android counters fire on buttons that leave for the Play Store. They still measure
   intent rather than installs, same as the Windows ones measure clicks rather than
   completed downloads.
*/
var DL_URL = "https://baopxmwebqfdubvgjsri.supabase.co/rest/v1/";
var DL_KEY = "sb_publishable_54t4NxwLHZqGuGNrDM9TrA_b7F3Dh3B";

function dlCount(table) {
  try {
    fetch(DL_URL + table, {
      method: "POST",
      headers: {
        "apikey": DL_KEY,
        "Authorization": "Bearer " + DL_KEY,
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
      },
      body: "{}"
    }).catch(function () {});
  } catch (e) {}
}

function rdCountDownload() { dlCount("downloads"); }               // Rack Detector
function rvCountDownload() { dlCount("downloads_rackviewer"); }    // Rack Viewer
function rtCountDownload() { dlCount("downloads_racktracker"); }   // Rack Tracker
function rsCountDownload() { dlCount("downloads_rackscorer"); }    // Rack Scorer
