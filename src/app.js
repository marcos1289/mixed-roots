const box = document.querySelector(".lightbox");
const boxImg = box.querySelector("img");
const boxCap = box.querySelector("figcaption");
let items = [];
let index = 0;

function show(i) {
  index = (i + items.length) % items.length;
  const t = items[index];
  boxImg.src = t.dataset.full;
  boxImg.alt = t.dataset.caption;
  boxCap.textContent = t.dataset.caption;
}

document.querySelectorAll(".thumb").forEach((t) => {
  t.addEventListener("click", () => {
    const group = t.closest("[data-lightbox-group]");
    items = [...(group || document).querySelectorAll(".thumb")];
    show(items.indexOf(t));
    box.showModal();
  });
});

box.querySelector(".lb-close").addEventListener("click", () => box.close());
box.querySelector(".lb-prev").addEventListener("click", () => show(index - 1));
box.querySelector(".lb-next").addEventListener("click", () => show(index + 1));
box.addEventListener("click", (e) => { if (e.target === box) box.close(); });
box.addEventListener("keydown", (e) => {
  if (e.key === "ArrowLeft") show(index - 1);
  if (e.key === "ArrowRight") show(index + 1);
});
box.addEventListener("close", () => { boxImg.removeAttribute("src"); });

document.querySelectorAll("video").forEach((v) => {
  v.addEventListener("play", () => {
    document.querySelectorAll("video").forEach((o) => { if (o !== v) o.pause(); });
  });
});
