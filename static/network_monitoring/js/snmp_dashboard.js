
document.addEventListener("DOMContentLoaded", () => {

    const deviceItems = document.querySelectorAll(".device-item");
    const deviceSearch = document.getElementById("device-search");
    const details = document.getElementById("selected-device-details");

    let selectedDeviceId = null;

    function selectDevice(button) {

        selectedDeviceId = button.dataset.deviceId;

        deviceItems.forEach(item => {
            item.classList.remove(
                "border-blue-500",
                "bg-blue-500/10"
            );

            item.classList.add("border-slate-800");
        });

        button.classList.remove("border-slate-800");

        button.classList.add(
            "border-blue-500",
            "bg-blue-500/10"
        );

        details.innerHTML = `
            <div class="flex flex-col sm:flex-row
                        sm:items-center justify-between gap-4">

                <div>
                    <p class="text-xs text-slate-500 mb-2">
                        SELECTED DEVICE
                    </p>

                    <h2 class="text-2xl font-bold">
                        ${escapeHTML(button.dataset.deviceName)}
                    </h2>

                    <p class="text-sm text-slate-400 mt-2">
                        ${escapeHTML(button.dataset.deviceHost)}
                    </p>
                </div>

                <span class="text-xs text-blue-400
                             bg-blue-500/10 rounded-lg px-3 py-2">
                    Device selected
                </span>

            </div>
        `;
    }

    function escapeHTML(value) {
        return String(value ?? "").replace(/[&<>"']/g, char => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#039;"
        })[char]);
    }

    deviceItems.forEach(button => {
        button.addEventListener("click", () => {
            selectDevice(button);
        });
    });

    if (deviceItems.length) {
        selectDevice(deviceItems[0]);
    }

    deviceSearch.addEventListener("input", () => {

        const query = deviceSearch.value.toLowerCase().trim();

        deviceItems.forEach(button => {

            const name = button.dataset.deviceName.toLowerCase();
            const host = button.dataset.deviceHost.toLowerCase();

            button.classList.toggle(
                "hidden",
                !name.includes(query) && !host.includes(query)
            );

        });

    });

});
