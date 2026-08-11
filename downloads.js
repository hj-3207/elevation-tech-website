/* Anonymous download-click counters, shared by rack-detector.html,
   rack-viewer.html and apps.html. Was duplicated inline across all three;
   extracted so the endpoint and key live in one place.

   Fire-and-forget: this can never block or break the actual download, which
   opens in a new tab. Only a timestamp is stored — no personal data. The
   publishable key is safe to expose, because RLS lets visitors INSERT only,
   never read or edit.

   Each app writes to its own table. `downloads` is Rack Detector's and has no
   app column, so Rack Viewer must NOT share it — doing so would silently fold
   Viewer clicks into the Detector count. Table definition for the second one:

     create table if not exists public.downloads_rackviewer (
       id bigint generated always as identity primary key,
       created_at timestamptz not null default now()
     );
     alter table public.downloads_rackviewer enable row level security;
     create policy "anon can insert download events"
       on public.downloads_rackviewer for insert to anon with check (true);
     grant insert on public.downloads_rackviewer to anon;
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

function rdCountDownload() { dlCount("downloads"); }
function rvCountDownload() { dlCount("downloads_rackviewer"); }
