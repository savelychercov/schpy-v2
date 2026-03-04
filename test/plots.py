import copy
import time

import matplotlib.pyplot as plt

from src import best_of, db, schedule_maker

if __name__ == "__main__":
    plot_data = []

    data = db.ExampleData()
    best_data = None
    best_schedule_obj = None
    best_rating = -1

    count_iterations = int(input("Введите количество итераций: "))
    update_every = 3  # seconds
    progressbar_length = 20
    passed_time = 0
    start_time = time.time()

    for iteration in range(1, count_iterations + 1):
        if (
            time.time() - (passed_time + start_time) > update_every
        ):  # condition: every 1 second
            passed_time = time.time() - start_time
            approx_time = count_iterations * passed_time / iteration
            remaining_time = approx_time - passed_time
            completion_percentage = round((iteration / count_iterations) * 100, 2)
            progressbar = (
                "["
                + (
                    "█" * (int(completion_percentage / 100 * progressbar_length))
                    + "▁"
                    * (
                        progressbar_length
                        - int(completion_percentage / 100 * progressbar_length)
                    )
                )
                + "]"
            )
            best_schedule_counts = best_of.get_counts(
                best_schedule_obj.pairs, best_data, best_schedule_obj.remaining_data
            )
            best_schedule_counts_str = (
                f"TG: {best_schedule_counts['teachers_gaps_count']}, "
                f"OPG: {best_schedule_counts['offline_pairs_gaps']}, "
                f"OT: {best_schedule_counts['overworked_teachers']}, "
                f"UH: {best_schedule_counts['unissued_hours']}"
            )
            print(
                f"Осталось времени: {str(round(remaining_time // 60)).rjust(2, '0') + 'м, ' if remaining_time >= 60 else ''}{str(round(remaining_time % 60)).rjust(2, '0')}с. {progressbar} {str(round(completion_percentage)).rjust(2, '0')}% / ({best_schedule_counts_str})"
            )

        data_copy = best_of.shuffle_data(data)
        schedule_obj = schedule_maker.make_full_schedule(data_copy)
        schedule_rating = best_of.rate_schedule(
            schedule_obj.pairs, data_copy, schedule_obj.remaining_data
        )
        if schedule_rating > best_rating:
            best_rating = schedule_rating
            del best_schedule_obj
            best_schedule_obj = copy.deepcopy(schedule_obj)
            best_data = copy.deepcopy(data_copy)
        else:
            del schedule_obj

        best_schedule_counts = best_of.get_counts(
            best_schedule_obj.pairs, best_data, best_schedule_obj.remaining_data
        )
        plot_data.append(
            (
                iteration,
                best_rating,
                best_schedule_counts["teachers_gaps_count"],
                best_schedule_counts["offline_pairs_gaps"],
                best_schedule_counts["overworked_teachers"],
                best_schedule_counts["unissued_hours"],
            )
        )

    print(f"Best schedule: {best_rating}")
    schedule_maker.print_schedule(best_schedule_obj.pairs)
    print(
        f"Teachers gaps: {best_of.count_teachers_gaps(best_data, best_schedule_obj.remaining_data)}"
    )
    print(
        f"Offline pairs gaps: {best_of.count_offline_pairs_gaps(best_schedule_obj.pairs, best_data)}"
    )
    print(
        f"Overworked teachers: {best_of.count_overworked_teachers(best_schedule_obj.pairs)}"
    )
    print(
        f"Unissued hours: {best_of.count_unissued_hours(best_schedule_obj.remaining_data)}"
    )

    plt.ylabel("Рейтинг")
    plt.xlabel("Итерации")
    plt.plot(
        range(1, count_iterations + 1),
        [x[1] for x in plot_data],
        linestyle="-",
        color="blue",
        label="Rating",
    )
    plt.text(
        count_iterations + 1,
        [x[1] for x in plot_data][-1],
        "Rating",
        fontsize=10,
        ha="left",
        color="white",
        bbox=dict(facecolor="#3e3852", alpha=0.9, linewidth=0, pad=0),
    )
    plt.savefig("rating_graph.png", bbox_inches="tight", dpi=300)
    plt.clf()

    plt.ylabel("Окна")
    plt.xlabel("Итерации")
    plt.plot(
        range(1, count_iterations + 1),
        [x[2] for x in plot_data],
        linestyle="-",
        color="red",
        label="Teachers gaps",
    )
    plt.savefig("teachers_gaps_graph.png", bbox_inches="tight", dpi=300)
    plt.clf()

    plt.plot(
        range(1, count_iterations + 1),
        [x[3] for x in plot_data],
        linestyle="-",
        color="green",
        label="Offline pairs gaps",
    )
    plt.text(
        count_iterations + 1,
        [x[3] for x in plot_data][-1],
        "Offline pairs gaps",
        fontsize=10,
        ha="left",
        color="white",
        bbox=dict(facecolor="#3e3852", alpha=0.9, linewidth=0, pad=0),
    )
    plt.savefig("offline_pairs_gaps_graph.png", bbox_inches="tight", dpi=300)
    plt.clf()

    plt.ylabel("Невыставленные часы")
    plt.xlabel("Итерации")
    plt.plot(
        range(1, count_iterations + 1),
        [x[5] for x in plot_data],
        linestyle="-",
        color="purple",
        label="Unissued hours",
    )
    plt.text(
        count_iterations + 1,
        [x[5] for x in plot_data][-1],
        "Unissued hours",
        fontsize=10,
        ha="left",
        color="white",
        bbox=dict(facecolor="#3e3852", alpha=0.9, linewidth=0, pad=0),
    )

    plt.savefig("unissued_hours_graph.png", bbox_inches="tight", dpi=300)
    # plt.show()
