/* This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
 *    Copyright (C) 2024
 *
 *  This program is free software: you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation, either version 3 of the License, or
 *  (at your option) any later version.
 *
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License
 *  along with this program. If not, see <http://www.gnu.org/licenses/>.
 */

/* global getPath */

// Initialize infinite scroll for shelf pages
// NOTE: This initialization has been moved to main.js to avoid duplicate initializations
// and conflicts. The code below is kept for reference but commented out.
/*
$(document).ready(function () {
    // Check if we're on a shelf page with infinite scroll enabled
    if ($(".load-more").length && $(".next").length && $(".load-more .book").length) {
        // Initialize infinite scroll for shelf pages
        var $loadMore = $(".load-more .row").infiniteScroll({
            debug: false,
            // selector for the paged navigation (it will be hidden)
            path: ".next",
            // selector for the NEXT link (to page 2)
            append: ".load-more .book",
            //extraScrollPx: 300
        });

        $loadMore.on(
            "append.infiniteScroll",
            function (event, response, path, data) {
                // Update pagination in the response
                $(".pagination")
                    .addClass("hidden")
                    .html(() => $(response).find(".pagination").html());
                if ($("body").hasClass("blur")) {
                    $(" a:not(.dropdown-toggle) ").removeAttr("data-toggle");
                }
                // Reinitialize isotope for new items if needed
                $(".load-more .row").isotope("appended", $(data), null);
            },
        );

        // Handle the scroll event for CaliBlur theme
        if ($("body").hasClass("blur")) {
            $(".col-sm-10").bind("scroll", function () {
                if (
                    $(this).scrollTop() + $(this).innerHeight() >=
                    $(this)[0].scrollHeight
                ) {
                    $loadMore.infiniteScroll("loadNextPage");
                    window.history.replaceState(
                        {},
                        null,
                        $loadMore.infiniteScroll("getAbsolutePath"),
                    );
                }
            });
        }
    }
});
*/
