const states = [];
let currentStateIdx = 0;
let isLive = true;

let mapStateCanvas = null;

function addMapState(state, gameCanvas) {
  mapStateCanvas = gameCanvas;

  console.log("drawing state");
  states.push(state);
  if (isLive) {
    currentStateIdx = states.length - 1;
  }
  render();
}

function render() {
  const currentState = states[currentStateIdx];
  console.log("Rendering state", currentStateIdx, currentState);
  drawMap(currentState, mapStateCanvas);
  renderControls();
}

function renderControls() {
  const div = document.getElementById("map_controls");
  if (div == null) return;
  div.innerHTML = "";

  const stepNumber = document.createElement("div");
  stepNumber.innerText = `${currentStateIdx + 1} / ${states.length}`;
  div.appendChild(stepNumber);
  div.appendChild(document.createElement("br"));

  const playPauseButton = document.createElement("button");
  playPauseButton.innerText = isLive ? "Pauza" : "Přehrávat";
  playPauseButton.onclick = () => {
    isLive = !isLive;
    render();
  };
  div.appendChild(playPauseButton);

  const controlsDiv = document.createElement("div");
  const prevButton = document.createElement("button");
  prevButton.innerText = "Předchozí";
  prevButton.onclick = () => {
    if (currentStateIdx > 0) {
      currentStateIdx--;
    }
    render();
  };
  controlsDiv.appendChild(prevButton);
  const nextButton = document.createElement("button");
  nextButton.innerText = "Následující";
  nextButton.onclick = () => {
    if (currentStateIdx < states.length - 1) {
      currentStateIdx++;
    }
    render();
  };
  controlsDiv.appendChild(nextButton);
  div.appendChild(controlsDiv);
}
