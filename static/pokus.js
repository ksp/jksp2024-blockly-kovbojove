// Elements
var canvas;
var canvasContext;
var workspace;

// Other vars
var playOn = false;
var game_idx = -1;
var xml_code;

function drawGrid() {
    canvasContext.clearRect(0, 0, canvas.width, canvas.height);
    // Horizontal lines
    for (var x = 0; x <= 500; x += 10) {
        canvasContext.moveTo(x, 0);
        canvasContext.lineTo(x, 500);
    }
    // Vertical lines
    for (var y = 0; y <= 500; y += 10) {
        canvasContext.moveTo(0, y);
        canvasContext.lineTo(500, y);
    }
    canvasContext.strokeStyle = '#000';
    canvasContext.stroke();
}

function play() {
    if (playOn) {
        return;
    }

    playOn = true;
    var xml = Blockly.Xml.workspaceToDom(workspace);
    xml_code = Blockly.Xml.domToText(xml);
    document.getElementById('xmlOutput').innerText = xml_code;
    performPlay();
}

function stop() {
    if (!playOn) {
        return;
    }

    playOn = false;
    game_idx = -1;
}

async function performPlay() {
    if (!playOn) {
        return;
    }

    const response = await fetch('/turn', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            'game_idx': game_idx,
            'xml_code': xml_code
        })
    });
    if (response.ok) {
        const positions = await response.json();
        // TODO paint positions
        console.log(positions.positions);
    } else {
        console.error("Backend didn't return square positions")
    }
}
