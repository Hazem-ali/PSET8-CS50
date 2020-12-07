function greet() {
    let name = document.querySelector("#name").value;
    if (name != "")
    {
        document.querySelector("#Hello").innerHTML = "Hello, " + name + " <3";


    }
}