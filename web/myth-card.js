const mythCardPalettes = {
  red: { name: "Red and black", accent: "#FF777D" },
  gold: { name: "Gold and black", accent: "#FFD174" },
  blue: { name: "Blue and black", accent: "#83BEFF" },
};

function drawVisualExample(example, palette) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 960;
  const context = canvas.getContext("2d");
  const { accent } = mythCardPalettes[palette];
  const font = "system-ui, sans-serif";
  const photoStart = example.photo ? 554 : 960;
  const margin = 44;
  const panelWidth = photoStart - margin * 2;

  function wrap(text, width) {
    const lines = [];
    let line = "";
    for (const word of text.split(" ")) {
      const next = line ? line + " " + word : word;
      if (context.measureText(next).width <= width) {
        line = next;
      } else {
        if (line) lines.push(line);
        line = word;
        if (context.measureText(word).width > width) return null;
      }
    }
    lines.push(line);
    return lines;
  }

  function drawCopy(text, x, y, width, height, maxSize, color) {
    for (let size = maxSize; size >= 22; size -= 2) {
      context.font = "800 " + size + "px " + font;
      const lines = wrap(text, width);
      const lineHeight = size * 1.16;
      if (!lines || lines.length * lineHeight > height) continue;
      context.fillStyle = color;
      context.textBaseline = "middle";
      const start = y + (height - (lines.length - 1) * lineHeight) / 2;
      lines.forEach((line, index) => context.fillText(line, x, start + index * lineHeight));
      return;
    }
    throw new Error("Shorten the image headline, value, or label to fit the card.");
  }

  function drawValue(item, y, dashed) {
    const height = 200;
    const valueWidth = Math.round(panelWidth * 0.35);
    context.fillStyle = "#1B1B21";
    context.fillRect(margin, y, panelWidth, height);
    context.strokeStyle = "#E2E2E7";
    context.lineWidth = 3;
    context.setLineDash(dashed ? [14, 10] : []);
    context.strokeRect(margin, y, panelWidth, height);
    context.setLineDash([]);
    drawCopy(item.value, margin + 24, y, valueWidth - 24, height, 124, accent);
    drawCopy(
      item.label.toUpperCase(), margin + valueWidth + 12, y,
      panelWidth - valueWidth - 36, height, 46, "#F7F7F8"
    );
  }

  context.fillStyle = "#101014";
  context.fillRect(0, 0, 960, 960);
  if (example.photo) {
    const width = 960 - photoStart;
    const scale = Math.max(width / example.photo.naturalWidth, 960 / example.photo.naturalHeight);
    const cropWidth = width / scale;
    const cropHeight = 960 / scale;
    context.drawImage(
      example.photo,
      (example.photo.naturalWidth - cropWidth) / 2,
      (example.photo.naturalHeight - cropHeight) / 2,
      cropWidth, cropHeight, photoStart, 0, width, 960
    );
  }
  context.fillStyle = accent;
  context.fillRect(margin, 65, 40, 5);
  drawCopy("RUMOR SMASHER", margin + 55, 47, panelWidth - 55, 40, 25, accent);
  drawCopy(example.heading.toUpperCase(), margin, 102, panelWidth, 225, 74, "#F7F7F8");
  drawValue(example.first, 353, false);
  drawValue(example.second, 594, true);
  drawCopy("ILLUSTRATIVE EXAMPLE", margin, 832, panelWidth, 60, 25, "#C7C7D0");

  const description = example.photoDescription ? " Photo: " + example.photoDescription : "";
  return {
    jpeg: canvas.toDataURL("image/jpeg", 0.92).split(",")[1],
    alt: example.heading + " " + example.first.value + " " + example.first.label + ". " +
      example.second.value + " " + example.second.label + "." + description,
    palette,
  };
}
