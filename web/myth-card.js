const mythCardPalettes = {
  red: { name: "Red and black", accent: "#FF777D" },
  gold: { name: "Gold and black", accent: "#FFD174" },
  blue: { name: "Blue and black", accent: "#83BEFF" },
};

function drawMythCard(myth, clarification, palette) {
  const canvas = document.createElement("canvas");
  canvas.width = 960;
  canvas.height = 960;
  const context = canvas.getContext("2d");
  const { accent } = mythCardPalettes[palette];
  const font = "system-ui, sans-serif";

  function wrap(text, width) {
    const lines = [];
    let line = "";
    for (const word of text.split(" ")) {
      const next = line ? `${line} ${word}` : word;
      if (context.measureText(next).width <= width) {
        line = next;
        continue;
      }
      if (line) lines.push(line);
      line = word;
      if (context.measureText(line).width > width) return null;
    }
    lines.push(line);
    return lines;
  }

  function drawCopy(text, y, height, maxSize) {
    for (let size = maxSize; size >= 24; size -= 2) {
      context.font = `700 ${size}px ${font}`;
      const lines = wrap(text, 724);
      const lineHeight = size * 1.24;
      if (lines && lines.length * lineHeight <= height) {
        context.fillStyle = "#F7F7F8";
        lines.forEach((line, index) => context.fillText(line, 116, y + index * lineHeight));
        return;
      }
    }
    throw new Error("Shorten the card text so it fits clearly.");
  }

  context.fillStyle = "#101014";
  context.fillRect(0, 0, 960, 960);
  context.fillStyle = accent;
  context.fillRect(66, 67, 50, 6);
  context.font = `700 24px ${font}`;
  context.fillText("FITNESS EVIDENCE STUDIO", 132, 78);
  context.fillStyle = "#1B1B21";
  context.fillRect(66, 123, 828, 316);
  context.strokeStyle = "#62626F";
  context.lineWidth = 2;
  context.setLineDash([10, 9]);
  context.strokeRect(66, 123, 828, 316);
  context.setLineDash([]);
  context.fillStyle = "#1B1B21";
  context.fillRect(66, 465, 828, 396);
  context.fillStyle = accent;
  context.fillRect(66, 465, 8, 396);
  context.font = `800 26px ${font}`;
  context.fillText("THE MYTH", 116, 176);
  context.fillText("THE CLARIFICATION", 116, 520);
  drawCopy(myth, 242, 210, 54);
  drawCopy(clarification, 587, 285, 52);

  context.fillStyle = "#C7C7D0";
  context.font = `500 22px ${font}`;
  context.fillText("Research source linked in the post", 66, 918);

  return {
    jpeg: canvas.toDataURL("image/jpeg", 0.92).split(",")[1],
    alt: `Myth: ${myth} Clarification: ${clarification}`,
    palette,
  };
}
