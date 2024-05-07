var ctx;
var width;
var height;
var squareHalf;
var squareSize;

// Hat color, "face" color.
const teamColors = {
    "red": ["#78281f", "#f1948a"],
    "green": ["#196f3d", "#82e0aa"],
    "blue": ["#1a5276", "#85c1e9"],
    "yellow": ["#9a7d0a", "#f7dc6f"],
    "pink": ["#c3c3c3", "#ec64e4"],
    "violet": ["#533073", "#922ced"],
    "olive": ["#637361", "#808000"],
    "maroon": ["#800000", "#bc001c"],
    "black": ["#96500f", "#000000"],
    "white": ["#000000", "#d3d3d3"],
    "gray": ["#808080", "#808080"]
};

function drawGrid(game_canvas) {
    ctx.strokeStyle = '#c2c2a3';
    for (let x = 0; x <= width; x++) {
        ctx.beginPath();
        ctx.moveTo(x * squareSize, 0);
        ctx.lineTo(x * squareSize, height * squareSize);
        ctx.stroke();
    }
    for (let y = 0; y <= height; y++) {
        ctx.beginPath();
        ctx.moveTo(0, y * squareSize);
        ctx.lineTo(width * squareSize, y * squareSize);
        ctx.stroke();
    }
}

function drawWall(x, y) {
    y = height - y - 1
    ctx.beginPath();
    ctx.fillStyle = "black";
    ctx.fillRect(x * squareSize, y * squareSize, squareSize, squareSize);
    ctx.closePath();
}

function drawCowboy(x, y, team) {
    y = height - y - 1
    let darkColor = teamColors[team][0];
    let lightColor = teamColors[team][1];

    ctx.fillStyle = lightColor;
    ctx.beginPath();
    ctx.ellipse((x * squareSize) + squareHalf, (y * squareSize) + squareHalf + (squareHalf / 4), squareSize / 4, squareSize / 3, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.closePath();

    ctx.fillStyle = darkColor;
    ctx.beginPath();
    ctx.fillRect(x * squareSize + (squareSize / 8), y *  squareSize + squareHalf, squareSize * 3 / 4, squareHalf / 6);
    ctx.fillRect(x * squareSize + (squareHalf / 2), y * squareSize + squareHalf / 2, squareHalf, squareSize / 3);
    ctx.closePath();
}

function drawBullet(x, y, team) {
    y = height - y - 1
    ctx.fillStyle = teamColors[team][0];
    ctx.beginPath();
    ctx.arc((x * squareSize) + squareHalf, (y * squareSize) + squareHalf, squareHalf / 3, 0, Math.PI * 2);
    ctx.fill();
    ctx.closePath();
}

function drawGold(x, y) {
    y = height - y - 1
    const centerX = (x * squareSize) + squareHalf;
    const centerY = (y * squareSize) + squareHalf;

    ctx.fillStyle = "#f5b041";
    ctx.beginPath();
    ctx.arc(centerX, centerY, squareHalf * 7 / 10, 0, Math.PI * 2);
    ctx.fill();
    ctx.closePath();

    ctx.fillStyle = "#f7dc6f";
    ctx.beginPath();
    ctx.arc(centerX, centerY, squareHalf * 5 / 10, 0, Math.PI * 2);
    ctx.fill();
    ctx.closePath();
}

function drawExplosion(x, y) {
    const beams = 8;
    const radius = squareSize / 3;
    y = height - y - 1;
    x = (squareSize * x) + squareHalf;
    y = (squareSize * y) + squareHalf;
    ctx.fillStyle = '#ffd700';
    for (let i = 0; i < beams; i++) {
        const angle = (Math.PI * 2 / beams) * i;
        const endX = x + Math.cos(angle) * radius;
        const endY = y + Math.sin(angle) * radius;

        // Draw a triangle from the center to current direction.
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(endX, endY);
        ctx.lineTo(endX + Math.cos(angle - Math.PI / 2) * radius, endY + Math.sin(angle - Math.PI / 2) * radius);
        ctx.closePath();
        ctx.fill();
    }
}

// Takes the (x, y) position of the cowboy and the direction shooting.
function drawFiringArrow(x, y, direction) {
    x = squareSize * x;
    y = squareSize * (height - y - 1);

    ctx.beginPath();
    switch (direction) {
        // W
        case 0:
            ctx.moveTo(x, y + squareSize / 2);
            ctx.lineTo(x + squareSize * 0.2, y + squareSize * 0.4);
            ctx.lineTo(x + squareSize * 0.2, y + squareSize * 0.6);
            break;
        // NW
        case 1:
            ctx.moveTo(x, y);
            ctx.lineTo(x + squareSize * 0.2, y + squareSize * 0.2);
            ctx.lineTo(x + squareSize * 0.2, y + squareSize * 0.4);
            break;
        // N
        case 2:
            ctx.moveTo(x + squareHalf, y);
            ctx.lineTo(x + squareHalf / 2, y + squareSize / 5);
            ctx.lineTo(x + squareHalf * 1.5, y + squareSize / 5);
            break;
        // NE
        case 3:
            ctx.moveTo(x + squareSize, y);
            ctx.lineTo(x + squareSize * 0.8, y + squareSize * 0.2);
            ctx.lineTo(x + squareSize * 0.8, y + squareSize * 0.4);
            break;
        // E
        case 4:
            ctx.moveTo(x + squareSize, y + squareSize / 2);
            ctx.lineTo(x + squareSize * 0.8, y + squareSize * 0.4);
            ctx.lineTo(x + squareSize * 0.8, y + squareSize * 0.6);
            break;
        // SE
        case 5:
            ctx.moveTo(x + squareSize, y + squareSize);
            ctx.lineTo(x + squareSize * 0.8, y + squareSize * 0.8);
            ctx.lineTo(x + squareSize * 0.8, y + squareSize * 0.6);
            break;
        // S
        case 6:
            ctx.moveTo(x + squareHalf, y + squareSize);
            ctx.lineTo(x + squareHalf / 2, y + squareSize * 0.8);
            ctx.lineTo(x + squareHalf * 1.5, y + squareSize * 0.8);
            break;
        // SW
        case 7:
            ctx.moveTo(x, y + squareSize);
            ctx.lineTo(x + squareSize * 0.2, y + squareSize * 0.8);
            ctx.lineTo(x + squareSize * 0.2, y + squareSize * 0.6);
            break;
        default:
            break;
    }
    ctx.closePath();
    ctx.fillStyle = 'black';
    ctx.fill();
}

function drawMap(data, game_canvas) {
    width = data["width"];
    height = data["height"];
    squareSize = game_canvas.width / width;
    squareHalf = squareSize / 2;

    if (game_canvas.height != squareSize * height) {
        console.log("CHANGED HEIGHT");
        game_canvas.height = squareSize * height;
    }

    ctx = game_canvas.getContext('2d');

    // Clear canvas
    ctx.clearRect(0, 0, game_canvas.width, game_canvas.height);

    // Draw all
    drawGrid();

    // Walls
    data["walls"].forEach((w) => drawWall(w[0], w[1]));

    // Golds
    data["golds"].forEach((g) => drawGold(g[0], g[1]));

    // Cowboys
    data["cowboys"].forEach((cb) => {
        // console.log(cb);
        drawCowboy(cb[0][0], cb[0][1], cb[1]);
    });

    // Bullets
    data["bullets"].forEach((b) => {
        // console.log(b);
        drawBullet(b[0][0], b[0][1], b[1]);
    });

    // Draw shooting directions:
    data["shot_directions"].forEach((sd) => drawFiringArrow(sd[0], sd[1], sd[2]));

    // Explosions
    data["explosions"].forEach((e) => drawExplosion(e[0], e[1]));
}
