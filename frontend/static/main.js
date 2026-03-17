async function send() {

    const file = document.getElementById("file").files[0]

    const formData = new FormData()
    formData.append("file", file)

    const response = await fetch("/process", {
        method: "POST",
        body: formData
    })

    const blob = await response.blob()

    const url = window.URL.createObjectURL(blob)

    const a = document.createElement("a")
    a.href = url
    a.download = "result.pdf"
    a.click()
}
