// Wait for the page to load before starting
window.onload = function() {
    // This is where we set up our drawing tools!
    const canvas = document.getElementById('drawingBoard');
    const ctx = canvas.getContext('2d');
    let isDrawing = false;
    let currentColor = 'red';
    let lastX = 0;
    let lastY = 0;

    // When the mouse button is pressed down
    canvas.addEventListener('mousedown', startDrawing);
    // When the mouse moves
    canvas.addEventListener('mousemove', draw);
    // When the mouse button is released
    canvas.addEventListener('mouseup', stopDrawing);
    // If mouse leaves the canvas
    canvas.addEventListener('mouseout', stopDrawing);

    // This function starts our drawing
    function startDrawing(event) {
        isDrawing = true;
        [lastX, lastY] = [
            event.clientX - canvas.getBoundingClientRect().left,
            event.clientY - canvas.getBoundingClientRect().top
        ];
    }

    // This function does the actual drawing
    function draw(event) {
        // Only draw if the mouse button is pressed
        if (!isDrawing) return;

        // Get where the mouse is on the canvas
        let x = event.clientX - canvas.getBoundingClientRect().left;
        let y = event.clientY - canvas.getBoundingClientRect().top;

        // Make our drawing look pretty
        ctx.beginPath();
        ctx.lineWidth = 10;
        ctx.lineCap = 'round';
        ctx.strokeStyle = currentColor;
        
        // Draw a line from the last position to current position
        ctx.moveTo(lastX, lastY);
        ctx.lineTo(x, y);
        ctx.stroke();

        // Update the last position
        [lastX, lastY] = [x, y];
    }

    // This function stops our drawing
    function stopDrawing() {
        isDrawing = false;
    }

    // Make these functions available globally
    window.setColor = function(color) {
        currentColor = color;
    }

    window.clearCanvas = function() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
} 