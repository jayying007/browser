var count = 0;
window.console.log("hello")
function callback() {
    var output = window.document.querySelectorAll("div")[1];
    output.innerHTML = "count: " + (count++);
    if (animate())
        window.requestAnimationFrame(callback);
}

var total_frames = 120;
var current_frame = 0;
var change_per_frame = (0.999 - 0.1) / total_frames;
function animate() {
    current_frame++;
    var new_opacity = current_frame * change_per_frame + 0.1;
    var div = window.document.querySelectorAll("div")[0];
    div.style = "opacity:" + new_opacity;
    return current_frame < total_frames;
}
window.requestAnimationFrame(callback);