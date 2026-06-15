#include <algorithm>
#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#ifdef _OPENMP
#include <omp.h>
#endif

struct Row {
    std::string customer_id;
    double churn_probability;
    double uplift_score;
    double clv;
    double coupon_cost;
    double expected_incremental_profit;
    double expected_roi;
};

static std::vector<std::string> split_csv_line(const std::string &line) {
    std::vector<std::string> out;
    std::string current;
    std::stringstream ss(line);
    while (std::getline(ss, current, ',')) out.push_back(current);
    return out;
}

static double to_double(const std::string &s, double fallback = 0.0) {
    try { return std::stod(s); } catch (...) { return fallback; }
}

int main(int argc, char **argv) {
    if (argc < 4) {
        std::cerr << "Usage: openmp_roi <input.csv> <output.csv> <threads>\n";
        return 2;
    }
    const std::string input_path = argv[1];
    const std::string output_path = argv[2];
    const int threads = std::max(1, std::stoi(argv[3]));

#ifdef _OPENMP
    omp_set_num_threads(threads);
#endif

    std::ifstream in(input_path);
    if (!in) {
        std::cerr << "Cannot open input: " << input_path << "\n";
        return 3;
    }

    std::string line;
    std::getline(in, line); // header
    std::vector<Row> rows;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        auto cols = split_csv_line(line);
        if (cols.size() < 5) continue;
        rows.push_back(Row{cols[0], to_double(cols[1]), to_double(cols[2]), to_double(cols[3]), to_double(cols[4]), 0.0, 0.0});
    }

    auto t0 = std::chrono::high_resolution_clock::now();
#pragma omp parallel for schedule(static)
    for (long long i = 0; i < static_cast<long long>(rows.size()); ++i) {
        Row &r = rows[static_cast<std::size_t>(i)];
        const double retained_value = r.uplift_score * r.churn_probability * r.clv;
        const double risk_penalty = 0.08 * r.churn_probability * r.coupon_cost;
        r.expected_incremental_profit = retained_value - r.coupon_cost - risk_penalty;
        r.expected_roi = (r.coupon_cost > 0.0) ? r.expected_incremental_profit / r.coupon_cost : 0.0;
    }
    auto t1 = std::chrono::high_resolution_clock::now();
    const double elapsed_ms = std::chrono::duration<double, std::milli>(t1 - t0).count();

    std::ofstream out(output_path);
    out << "customer_id,churn_probability,uplift_score,clv,coupon_cost,expected_incremental_profit,expected_roi\n";
    out << std::fixed << std::setprecision(8);
    for (const auto &r : rows) {
        out << r.customer_id << ',' << r.churn_probability << ',' << r.uplift_score << ',' << r.clv << ',' << r.coupon_cost << ','
            << r.expected_incremental_profit << ',' << r.expected_roi << '\n';
    }
    std::cerr << "openmp_rows=" << rows.size() << " threads=" << threads << " elapsed_ms=" << elapsed_ms << "\n";
    return 0;
}
