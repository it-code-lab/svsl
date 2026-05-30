let rowCounter = 0;

function addRow() {
  rowCounter += 1;
  const rowId = String(Date.now()) + "_" + String(rowCounter);
  const template = document.getElementById("rowTemplate").innerHTML
    .replaceAll("__ROW_ID__", rowId)
    .replaceAll("__ROW_NUM__", rowCounter);

  const wrapper = document.createElement("div");
  wrapper.innerHTML = template;
  document.getElementById("rows").appendChild(wrapper.firstElementChild);
}

function removeRow(button) {
  const row = button.closest(".video-row");
  if (row) row.remove();
}

function applyDefaults() {
  const bulk = {
    title: document.getElementById("bulkTitle").value,
    description: document.getElementById("bulkDescription").value,
    tags: document.getElementById("bulkTags").value,
    scheduled: document.getElementById("bulkScheduled").value,
    channel: document.getElementById("bulkChannel").value,
    playlist: document.getElementById("bulkPlaylist").value,
    facebookPage: document.getElementById("bulkFacebookPage").value,
    pinterestBoard: document.getElementById("bulkPinterestBoard").value,
  };

  document.querySelectorAll(".video-row").forEach((row, index) => {
    const title = row.querySelector('input[name^="title_"]');
    const description = row.querySelector('textarea[name^="description_"]');
    const tags = row.querySelector('input[name^="tags_"]');
    const scheduled = row.querySelector('input[name^="scheduled_at_"]');
    const channel = row.querySelector('input[name^="channel_name_"]');
    const playlist = row.querySelector('input[name^="playlist_"]');
    const facebookPage = row.querySelector('select[name^="facebook_page_id_"]');
    const pinterestBoard = row.querySelector('select[name^="pinterest_board_id_"]');

    if (title && !title.value && bulk.title) {
      title.value = bulk.title + " " + (index + 1);
    }
    if (description && !description.value) description.value = bulk.description;
    if (tags && !tags.value) tags.value = bulk.tags;
    if (scheduled && !scheduled.value) scheduled.value = bulk.scheduled;
    if (channel && !channel.value) channel.value = bulk.channel;
    if (playlist && !playlist.value) playlist.value = bulk.playlist;
    if (facebookPage && !facebookPage.value) facebookPage.value = bulk.facebookPage;
    if (pinterestBoard && !pinterestBoard.value) pinterestBoard.value = bulk.pinterestBoard;
  });
}
