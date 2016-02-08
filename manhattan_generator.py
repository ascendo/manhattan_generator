"""
    manhattan_generator
    ~~~~~~~~~~~~~~~~~~~

    Help creating beautiful graphs of linkage results

    Version: 1.6

    Author: Louis-Philippe Lemieux Perreault

    Email:  louis-philippe.lemieux.perreault@statgen.org

"""


import os
import sys
import argparse
import numpy as np


__version__ = "1.6.0"


desc = """This is version {} of manhattan_generator.

The user needs to specify the type of graph to create (between 'two-point'
or 'multipoint') with the corresponding options.
""".format(__version__)
parser = argparse.ArgumentParser(description=desc)
parser.add_argument("-v", "--version", action="version",
                    version="%(prog)s {}".format(__version__))


class DraggableAnnotation:
    """Creates draggable annotations for markers."""
    lock = None  # only one can be animated at a time

    def __init__(self, annot):
        """Creates an annotation which is draggable."""
        self.annot = annot
        self.press = None
        self.background = None

    def connect(self):
        """Connect to all the events we need."""
        self.cidpress = self.annot.figure.canvas.mpl_connect(
            'button_press_event', self.on_press)
        self.cidrelease = self.annot.figure.canvas.mpl_connect(
            'button_release_event', self.on_release)
        self.cidmotion = self.annot.figure.canvas.mpl_connect(
            'motion_notify_event', self.on_motion)

    def on_press(self, event):
        "On button press, we will see if the mouse is over and store data."""
        if event.inaxes != self.annot.axes:
            return
        if DraggableAnnotation.lock is not None:
            return
        contains, attrd = self.annot.contains(event)
        if not contains:
            return
        x0, y0 = None, None
        if not hasattr(self.annot, "xyann"):
            # Quick fix for a deprecation in annotation...
            x0, y0 = self.annot.xytext
        else:
            x0, y0 = self.annot.xyann
        self.press = x0, y0, event.xdata, event.ydata
        DraggableAnnotation.lock = self

        # draw everything but the selected annotation and store the pixel
        # buffer
        canvas = self.annot.figure.canvas
        axes = self.annot.axes
        self.annot.set_animated(True)
        canvas.draw()
        self.background = canvas.copy_from_bbox(self.annot.axes.bbox)

        # now redraw just the annotation
        axes.draw_artist(self.annot)

        # and blit just the redrawn area
        canvas.blit(axes.bbox)

    def on_motion(self, event):
        """On motion we will move the annot if the mouse is over us."""
        if DraggableAnnotation.lock is not self:
            return
        if event.inaxes != self.annot.axes:
            return
        x0, y0, xpress, ypress = self.press
        dx = event.xdata - xpress
        dy = event.ydata - ypress
        if not hasattr(self.annot, "xyann"):
            # Quick fix for a deprecation in annotation...
            self.annot.xytext = (x0+dx, y0+dy)
        else:
            self.annot.xyann = (x0+dx, y0+dy)

        canvas = self.annot.figure.canvas
        axes = self.annot.axes
        # restore the background region
        canvas.restore_region(self.background)

        # redraw just the current annotation
        axes.draw_artist(self.annot)

        # blit just the redrawn area
        canvas.blit(axes.bbox)

    def on_release(self, event):
        """On release we reset the press data."""
        if DraggableAnnotation.lock is not self:
            return

        self.press = None
        DraggableAnnotation.lock = None

        # turn off the annot animation property and reset the background
        self.annot.set_animated(False)
        self.background = None

        # redraw the full figure
        self.annot.figure.canvas.draw()

    def disconnect(self):
        "Disconnect all the stored connection ids."""
        self.annot.figure.canvas.mpl_disconnect(self.cidpress)
        self.annot.figure.canvas.mpl_disconnect(self.cidrelease)
        self.annot.figure.canvas.mpl_disconnect(self.cidmotion)


class ProgramError(Exception):
    """An :py:class:`Exception` raised in case of a problem.

    :param msg: the message to print to the user before exiting.
    :type msg: string

    """
    def __init__(self, msg):
        """Construction of the :py:class:`ProgramError` class.

        :param msg: the message to print to the user
        :type msg: string

        """
        self.message = str(msg)

    def __str__(self):
        """Creates a string representation of the message."""
        return self.message


def main():
    """The main method of the program."""
    # Getting and checking the options
    args = parseArgs()
    checkArgs(args)

    # Reading the input file for two point linkage
    two_point = None
    if args.twopoint is not None:
        two_point = read_input_file(args.twopoint, args.phys_pos_flag,
                                    args.use_pvalues_flag, args)

    # Reading the input file for multipoint linkage
    multi_point = None
    if args.multipoint is not None:
        multi_point = read_input_file(args.multipoint, args.phys_pos_flag,
                                      args.use_pvalues_flag, args)

    # Creating the plots
    create_manhattan_plot(two_point, multi_point, args)


def read_input_file(inFileName, use_physical_positions, use_pvalues, options):
    """Reads input file.

    :param inFileName: the name of the input file
    :type inFileName: string

    :param use_physical_positions: use physical position (bp) rather than
                                   genetic position (cM)?
    :type use_physical_positions: boolean

    :param use_pvalues: use *p values* instead of *lod score*?
    :type use_pvalues: boolean

    :returns: a :py:class:`numpy.recarray` with the following names: ``chr``,
              ``pos``, ``name`` and ``conf``.

    This function reads any kind of input file, as long as the file is
    tab-separated and that it contains columns with the following headers:

    ======================  ===============================================
            Header                           Description
    ======================  ===============================================
    ``chr``                 The name of the chromosome
    ``name``                The name of the marker
    ``pos`` or ``cm``       The physical or genetic position (respectively)
    ``lod`` or ``p_value``  The confidence value (either *lod score* or *p
                            value*, respectively)
    ======================  ===============================================

    .. note::

        If there is a problem while reading the input file(s),
        a :py:class:`ProgramError` will be raised, and the program will be
        terminated.

    """
    # The type of the data
    inFile = open(inFileName, 'r')

    # The data of the file
    data = []

    headerIndex = {}
    for line_nb, line in enumerate(inFile):
        row = line.rstrip("\r\n").split("\t")

        if line_nb == 0:
            # This is the header
            headerIndex = dict([(colName, i) for i, colName in enumerate(row)])
            colNames = [options.col_chr, options.col_name]
            if use_physical_positions:
                colNames.append(options.col_pos)
            else:
                colNames.append(options.col_cm)
            if use_pvalues:
                colNames.append(options.col_pvalue)
            else:
                colNames.append(options.col_lod)
            for colName in colNames:
                if colName not in headerIndex:
                    msg = "%(inFileName)s: no column named " \
                          "%(colName)s" % locals()
                    raise ProgramError(msg)
            continue

        # Getting the chromosome
        chromosome = encode_chr(row[headerIndex[options.col_chr]])

        # Do we skip this chromosome?
        if chromosome in options.exclude_chr:
            continue

        # Getting the position
        position = None
        try:
            position = map(
                [float, int][use_physical_positions],
                [row[headerIndex[[options.col_cm,
                                  options.col_pos][use_physical_positions]]]]
            )[0]
        except ValueError:
            msg = "%s: invalid position in %s" % (
                row[headerIndex[[options.col_cm,
                                 options.col_pos][use_physical_positions]]],
                inFileName,
            )
            raise ProgramError(msg)

        # Getting the confidence
        confidence = row[headerIndex[[options.col_lod,
                                      options.col_pvalue][use_pvalues]]]
        if confidence.upper() == "NA" or confidence.upper() == "NAN":
            continue
        try:
            confidence = float(confidence)
        except ValueError:
            msg = "%s: invalid confidence in %s" % (
                row[headerIndex[[options.col_lod,
                                 options.col_pvalue][use_pvalues]]],
                inFileName,
            )
            raise ProgramError(msg)

        # Getting the marker name
        name = row[headerIndex[options.col_name]]

        # Appending the data
        data.append((chromosome, position, name, confidence))

    # Closing the input file
    inFile.close()

    # Creating the numpy recarray
    data = np.array(
        data,
        dtype=[("chr", int),
               ("pos", [float, int][use_physical_positions]),
               ("name", "a%d" % max([len(i[2]) for i in data])),
               ("conf", float)],
    )
    data.sort(order=["chr", "pos"])

    if use_pvalues:
        # We need to transfort the values
        data["conf"] = -1 * np.log10(data["conf"])

    return data


def create_manhattan_plot(twopoint, multipoint, args):
    """Creates the manhattan plot from marker data.

    :param twopoint: the two point data (``None`` if not available).
    :type twopoint: :py:class:`numpy.recarray`

    :param multipoint: the multipoint data (``None`` if not available).
    :type multipoint: :py:class:`numpy.recarray`

    :param args: the options and arguments of the program.
    :type args: :py:class:`Namespace` from :py:mod:`argparse`

    Creates manhattan plots from two point or multipoint data. Two point
    results are shown in a manhattan plot using points (different color for
    each of the chromosomes). Multi point results are shown using lines.

    If both two and mutli point data are available, multi point results are
    shown above two point data.

    """
    import matplotlib as mpl
    from _tkinter import TclError
    if args.no_annotation:
        mpl.use("Agg")
    import matplotlib.pyplot as plt
    if args.no_annotation:
        plt.ioff()

    # The available chromosomes
    availableChr = []
    if args.twopoint is not None:
        availableChr.append(sorted(list(np.unique(twopoint["chr"]))))
    if args.multipoint is not None:
        availableChr.append(sorted(list(np.unique(multipoint["chr"]))))
    if len(availableChr) == 1:
        availableChr = availableChr[0]
    else:
        if availableChr[0] != availableChr[1]:
            msg = "missing chromsoome in either twopoint or multipoint data"
            raise ProgramError(msg)
        availableChr = availableChr[0]
    availableChr = map(int, availableChr)

    # Creating the figure
    figure = None
    try:
        figure = plt.figure(figsize=(args.graph_width, args.graph_height),
                            frameon=True)
    except TclError:
        msg = ("There is no available display, but annotation has been asked "
               "for...\nTry using the --no_annotation option.")
        raise ProgramError(msg)

    # Getting the maximum and minimum of the confidence value
    conf_min = [0.0]
    conf_max = []
    if args.twopoint is not None:
        conf_min.append(np.min(twopoint["conf"]))
        conf_max.append(np.max(twopoint["conf"]))
    if args.multipoint is not None:
        conf_min.append(np.min(multipoint["conf"]))
        conf_max.append(np.max(multipoint["conf"]))
    conf_min = min(conf_min)
    conf_max = max(conf_max)
    if args.max_ylim is not None:
        conf_max = args.max_ylim
    if args.min_ylim is not None:
        conf_min = args.min_ylim
    if args.no_negative_values or args.use_pvalues_flag:
        conf_min = 0.0

    # The chromosome spacing
    chr_spacing = [25.0, 25000000][args.phys_pos_flag]

    # Creating the ax and modify it
    ax = figure.add_subplot(111)
    ax.xaxis.set_ticks_position("none")
    ax.yaxis.set_ticks_position("left")
    ax.set_ylabel("LOD")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.set_xticks([])
    ax.set_xticklabels([])
    if args.use_pvalues_flag:
        ax.set_ylabel(r'$-\log_{10}$ (p value)', fontsize=args.label_text_size)
    else:
        ax.set_ylabel(unicode(args.graph_y_label, "utf-8"),
                      fontsize=args.label_text_size)
    ax.set_xlabel(unicode(args.graph_x_label, "utf-8"),
                  fontsize=args.label_text_size)
    ax.set_title(unicode(args.graph_title, "utf-8"), fontsize=16,
                 weight="bold")

    # Now plotting for each of the chromosome
    startingPos = 0
    annots = []
    ticks = []
    for i, chromosome in enumerate(availableChr):
        chr_twopoint = None
        chr_multipoint = None
        maxPos = []
        if args.twopoint is not None:
            chr_twopoint = twopoint[np.where(twopoint["chr"] == chromosome)]
            maxPos.append(np.max(chr_twopoint["pos"]))
        if args.multipoint is not None:
            chr_multipoint = multipoint[
                np.where(multipoint["chr"] == chromosome)
            ]
            maxPos.append(np.max(chr_multipoint["pos"]))
        maxPos = max(maxPos)

        # The color of the points
        color = [args.even_chromosome_color,
                 args.odd_chromosome_color][i % 2 == 0]
        multipoint_color = color

        # The box
        xmin = startingPos - (chr_spacing/2.0)
        xmax = maxPos+startingPos + (chr_spacing/2.0)
        if i % 2 == 1:
            ax.axvspan(xmin=xmin, xmax=xmax, color=args.chromosome_box_color)

        # The chromosome label
        ticks.append((xmin+xmax)/2.0)

        # Plotting the twopoint
        if args.twopoint is not None:
            ax.plot(chr_twopoint["pos"] + startingPos, chr_twopoint["conf"],
                    marker="o", ms=args.point_size, mfc=color,
                    mec=color, ls="None")
            multipoint_color = args.multipoint_color

        # Plotting the multipoint
        if args.multipoint is not None:
            ax.plot(chr_multipoint["pos"] + startingPos,
                    chr_multipoint["conf"], ls="-", color=multipoint_color,
                    lw=1.2)

        # Plotting the abline
        for abline_position in args.abline:
            ax.axhline(y=abline_position, color="black", ls="--", lw=1.2)
        if conf_min < 0:
            ax.axhline(y=0, color="black", ls="-", lw=1.2)

        # Plotting the significant markers
        if args.twopoint is not None:
            sigMask = chr_twopoint["conf"] >= args.significant_threshold
            ax.plot(chr_twopoint["pos"][sigMask] + startingPos,
                    chr_twopoint["conf"][sigMask], marker="o",
                    ls="None", ms=args.significant_point_size,
                    mfc=args.significant_color, mec=args.significant_color)

            # If we want annotation
            if not args.no_annotation:
                for j in np.where(sigMask)[0]:
                    # The confidence to write
                    theConf = "%.3f" % chr_twopoint["conf"][j]
                    if args.use_pvalues_flag:
                        theConf = str(10**(-1*chr_twopoint["conf"][j]))

                    # The label of the annotation
                    label = "\n".join([chr_twopoint["name"][j], theConf])

                    annot = ax.annotate(
                        label,
                        xy=(chr_twopoint["pos"][j]+startingPos,
                            chr_twopoint["conf"][j]),
                        xycoords="data",
                        size=10,
                        xytext=(chr_twopoint["pos"][j]+startingPos, conf_max),
                        va="center",
                        bbox=dict(boxstyle="round", fc="white", ec="black"),
                        textcoords="data",
                        arrowprops=dict(arrowstyle="->", shrinkA=6, shrinkB=5),
                    )
                    annots.append(annot)

        # Changing the starting point for the next chromosome
        startingPos = maxPos + startingPos + chr_spacing

    # Make them draggable
    drs = []
    for annot in annots:
        dr = DraggableAnnotation(annot)
        dr.connect()
        drs.append(dr)

    # Setting the limits
    padding = 0.39
    if args.no_y_padding:
        padding = 0
    ax.set_ylim(conf_min-padding, conf_max+padding)
    ax.set_xlim(0-chr_spacing, startingPos+chr_spacing)

    # Putting the xticklabels
    ax.set_xticks(ticks)
    ax.set_xticklabels(availableChr)

    for tick in ax.yaxis.get_major_ticks():
        tick.label.set_fontsize(args.axis_text_size)

    for tick in ax.xaxis.get_major_ticks():
        tick.label.set_fontsize(args.chr_text_size)

    # Saving or plotting the figure
    mpl.rcParams['savefig.dpi'] = args.dpi
    mpl.rcParams['ps.papersize'] = "auto"
    mpl.rcParams['savefig.orientation'] = "landscape"

    if args.no_annotation or (args.twopoint is None):
        # Annotation is for two-point only, se we save the figure
        plt.savefig(args.outFile_name + "." + args.graph_format,
                    bbox_inches="tight")
        if args.graph_format != "png":
            plt.savefig(args.outFile_name + ".png", bbox_inches="tight")
        if args.web:
            print args.outFile_name + ".png"

    else:
        # There is some two-point data and annotation is asked, se we show
        # the figure
        plt.show()


def encode_chr(chromosome):
    """Encode a chromosome in integer format.

    :param chromosome: the chromosome to encode in integer.
    :type chromosome: string

    :returns: the chromosome encoded in integer instead of string.

    This function encodes sex chromosomes, pseudo-autosomal regions and
    mitochondrial chromosomes in 23, 24, 25 and 26, respectively. If the
    chromosome is none of the above, the function returns the integer
    representation of the chromosome, if possible.

    .. note::

        If the chromosome is invalid, a :py:class:`ProgramError` will be
        raised, and the program terminated.

    .. warning::

        No check is done whether the chromosome is higher than 26 and below 1.
        As long as the chromosome is an integer or equal to ``X``, ``Y``,
        ``XY`` or ``MT``, no :py:class:`ProgramError` is raised.

    """
    chromosome = chromosome.upper()
    if chromosome == 'X':
        return 23
    elif chromosome == 'Y':
        return 24
    elif chromosome == 'XY':
        return 25
    elif chromosome == 'MT':
        return 26
    try:
        return int(chromosome)
    except ValueError:
        msg = "%(chromosome)s: not a valid chromosome" % locals()
        raise ProgramError(msg)


def checkArgs(args):
    """Checks the arguments and options.

    :param args: a :py:class:`Namespace` object containing the options of the
                 program.
    :type args: :py:class:`argparse.Namespace`

    :returns: ``True`` if everything was OK, ``False`` otherwise.

    If there is a problem with an option, an exception is raised using the
    :py:class:`ProgramError` class, a message is printed to the
    :class:`sys.stderr` and the program exists with code 1.

    """
    if (args.max_ylim is not None) and (args.min_ylim is not None):
        if args.max_ylim <= args.min_ylim:
            msg = "Y max limit (%f) is <= Y min limit " \
                  "(%f)" % (args.max_ylim, args.min_ylim)
            raise ProgramError(msg)

    # The type of graph
    if (args.twopoint is None) and (args.multipoint is None):
        msg = "Meed to specify at least one graph type (option -t or -m)"
        raise ProgramError(msg)

    # Check for input file (two-point)
    if args.twopoint is not None:
        if not os.path.isfile(args.twopoint):
            msg = "%s: no such file or directory" % args.twopoint
            raise ProgramError(msg)

    # Check for input file (multipoint)
    if args.multipoint is not None:
        if not os.path.isfile(args.multipoint):
            msg = "%s: no such file or directory" % args.multipoint
            raise ProgramError(msg)

    try:
        args.abline = [float(i) for i in args.abline.split(',')]
    except ValueError:
        msg = "%s: not a valid LOD score (must be float)" % args.abline
        raise ProgramError(msg)

    # Checking if there are some chromosome to exclude
    if args.exclude_chr is None:
        args.exclude_chr = set()
    else:
        args.exclude_chr = {encode_chr(i) for i in args.exclude_chr.split(",")}

    return True


def parseArgs():
    """Parses the command line options and arguments.

    :returns: A :py:class:`numpy.Namespace` object created by the
              :py:mod:`argparse` module. It contains the values of the
              different options.

    ============================  =======  ====================================
         Options                   Type                   Description
    ============================  =======  ====================================
    ``--twopoint``                File     The input *file* for two-point
                                           linkage
    ``--multipoint``              File     The input *file* for multipoint
                                           linkage
    ``--output``                  String   The name of the ouput *file*
    ``--format``                  String   The format of the plot (ps, pdf
                                           png)
    ``--dpi``                     Int      The quality of the output (in dpi)
    ``--bp``                      Boolean  Use physical positions (bp) instead
                                           of genetic positions (cM).
    ``--use-pvalues``             Boolean  Use pvalues instead of LOD score
                                           requires to compute
                                           :math:`-log_{10}(pvalue)`
    ``--no-negative-values``      Boolean  Do not plot negative values
    ``--max-ylim``                Float    The maximal Y *value* to plot
    ``--min-ylim``                Float    The minimal Y *value* to plot
    ``--graph-title``             String   The *title* of the graph
    ``--graph-xlabel``            String   The *text* for the x label
    ``--graph-ylabel``            String   The *text* for the y label
    ``--graph-width``             Int      The *width* of the graph, in
                                           inches
    ``--graph-height``            Int      The *height* of the graph, in
                                           inches
    ``--point-size``              Float    The *size* of each points.
    ``--significant-point-size``  Float    The *size* of each significant
                                           points
    ``--abline``                  String   The y *value* where to create a
                                           horizontal line, separated by a
                                           comma
    ``--significant-threshold``   Float    The significant threshold for
                                           linkage
    ``--no-annotation``           Boolean  Do not draw annotation (SNP names)
                                           for the significant results
    ``--chromosome-box-color``    String   The *color* for the box surrounding
                                           even chromosome numbers
    ``--even-chromosome-color``   String   The *color* for the box surrounding
                                           even chromosome numbers
    ``--odd-chromosome-color``    String   The *color* for the box surrounding
                                           odd chromosome numbers
    ``--multipoint-color``        String   The *color* for the multipoint plot
    ``--significant-color``       String   The *color* for points representing
                                           significant linkage
    ============================  =======  ====================================

    .. note::

        No option check is done here (except for the one automatically done
        by :py:mod:`argparse`. Those need to be done elsewhere
        (see :py:func:`checkArgs`).

    """

    # The input options
    group = parser.add_argument_group(
        "Input Options",
        "Options for the input file(s) (name of the file, type of graph, "
        "etc.).",
    )

    # The input file (for two point)
    group.add_argument("--twopoint", type=str, metavar="FILE",
                       help="The input FILE for two-point linkage.")

    # The input file (for multipoint)
    group.add_argument("--multipoint", type=str, metavar="FILE",
                       help="The input FILE for multipoint linkage.")

    # The column options
    group = parser.add_argument_group("Column Options",
                                      "The name of the different options.")

    # The chromosome column
    group.add_argument("--col-chr", type=str, metavar="COL", default="chr",
                       help=("The name of the column containing the "
                             "chromosomes [Default: %(default)s]."))

    # The marker name column
    group.add_argument("--col-name", type=str, metavar="COL", default="name",
                       help=("The name of the column containing the marker "
                             "names [Default: %(default)s]."))

    # The marker position column
    group.add_argument("--col-pos", type=str, metavar="COL", default="pos",
                       help=("The name of the column containing the marker "
                             "positions [Default: %(default)s]."))

    # The marker cM column
    group.add_argument("--col-cm", type=str, metavar="COL", default="cm",
                       help=("The name of the column containing the marker "
                             "cM [Default: %(default)s]."))

    # The marker p value
    group.add_argument("--col-pvalue", type=str, metavar="COL",
                       default="p_value",
                       help=("The name of the column containing the marker "
                             "p values [Default: %(default)s]"))

    # The marker lod score
    group.add_argument("--col-lod", type=str, metavar="COL", default="lod",
                       help=("The name of the column containing the marker "
                             "LOD score [Default: %(default)s]"))

    # The output options
    group = parser.add_argument_group("Graph Output Options",
                                      ("Options for the ouput file (name of "
                                       "the file, type of graph, etc.)."))

    # The output file name
    group.add_argument("-o", "--output", dest="outFile_name", type=str,
                       default="manhattan", metavar="NAME",
                       help=("The NAME of the ouput file [Default: "
                             "%(default)s]."))

    # The type of the graph (png, ps or pdf)
    format_choices = ["ps", "pdf", "png", "eps"]
    group.add_argument("-f", "--format", dest="graph_format", type=str,
                       default="png", metavar="FORMAT",
                       choices=format_choices,
                       help=("The FORMAT of the plot ({}) [Default: "
                             "%(default)s].".format(",".join(format_choices))))

    group.add_argument("--web", action="store_true",
                       help=("Always write a PNG file for web display, and "
                             "return the path of the PNG file."))

    group.add_argument("--dpi", type=int, default=600, metavar="INT",
                       help=("The quality of the output (in dpi) [Default: "
                             "%(default)d]."))

    # The graph type options
    group = parser.add_argument_group("Graph Options",
                                      ("Options for the graph type "
                                       "(two-point, multipoint, etc.)."))

    # Use physical position instead of genetic posiition
    group.add_argument("--bp", dest="phys_pos_flag", action="store_true",
                       help=("Use physical positions (bp) instead of "
                             "genetic positions (cM)."))

    # Using p values instead of LOD score
    group.add_argument("--use-pvalues", dest='use_pvalues_flag',
                       action="store_true",
                       help=("Use pvalues instead of LOD score. Requires "
                             "to compute -log10(pvalue)."))

    # Exclude some chromosomes
    group.add_argument("--exclude-chr", metavar="STRING",
                       help=("Exclude those chromosomes (list of chromosomes, "
                             "separated by a coma) [Default: None]."))

    # The graph presentation options
    group = parser.add_argument_group("Graph Presentation Options",
                                      ("Options for the graph presentation "
                                       "(title, axis label, etc.)."))

    # print negative values
    group.add_argument("--no-negative-values", action="store_true",
                       help="Do not plot negative values.")

    # The maximal y limit of the graph
    group.add_argument("--max-ylim", type=float, metavar="FLOAT",
                       help=("The maximal Y value to plot [Default: maximum "
                             "of max(LOD) and 1+significant-threshold]."))

    # The minimal y limit of the graph
    group.add_argument("--min-ylim", type=float, default=-2.0,
                       metavar="FLOAT", help="The minimal Y value to plot "
                                             "[Default: %(default).1f].")

    # Do we want padding?
    group.add_argument("--no-y-padding", action="store_true",
                       help="Do not add Y padding to the Y limit")

    # The graph's title
    group.add_argument("--graph-title", type=str, dest='graph_title',
                       default="", metavar="TITLE",
                       help="The TITLE of the graph [Default: empty].")

    # The graph's x label
    group.add_argument("--graph-xlabel", dest='graph_x_label', type=str,
                       default="Chromosome", metavar="TEXT",
                       help=("The TEXT for the x label. [Default: "
                             "%(default)s]."))

    # The graph's y label
    group.add_argument("--graph-ylabel", dest='graph_y_label', type=str,
                       default="LOD", metavar="TEXT",
                       help=("The TEXT for the y label. [Default: "
                             "%(default)s]."))

    # The graph width
    group.add_argument("--graph-width", type=int, default=14, metavar="WIDTH",
                       help=("The WIDTH of the graph, in inches [Default: "
                             "%(default)d]."))

    # The graph height
    group.add_argument("--graph-height", type=int, default=7,
                       metavar="HEIGHT",
                       help=("The HEIGHT of the graph, in inches [Default: "
                             "%(default)d]."))

    # The size of each point
    group.add_argument("--point-size", type=float, default=2.1,
                       metavar="SIZE", help=("The SIZE of each points "
                                             "[Default: %(default).1f]."))

    # The size of each significant point
    group.add_argument("--significant-point-size", type=float, default=4.5,
                       metavar="SIZE",
                       help=("The SIZE of each significant points "
                             "[Default: %(default).1f]."))

    # The ablines positions
    group.add_argument("--abline", type=str, default="3,-2",
                       metavar="POS1,POS2,...",
                       help=("The y value where to create a horizontal "
                             "line, separated by a comma [Default: "
                             "%(default)s]."))

    # The significant threshold
    group.add_argument("--significant-threshold", type=float, default=3.0,
                       metavar="FLOAT",
                       help=("The significant threshold for linkage or "
                             "association [Default: %(default).1f]"))

    # The annotation flag
    group.add_argument("--no-annotation", action="store_true",
                       help=("Do not draw annotation (SNP names) for the "
                             "significant results."))

    # The size of the text
    group.add_argument("--axis-text-size", type=int, default=12, metavar="INT",
                       help="The axis font size [Default: %(default)d]")

    group.add_argument("--chr-text-size", type=int, default=12, metavar="INT",
                       help="The axis font size [Default: %(default)d]")

    group.add_argument("--label-text-size", type=int, default=12,
                       metavar="INT", help="The axis font size "
                                           "[Default: %(default)d]")

    # The graph color options
    group = parser.add_argument_group("Graph Colors Options",
                                      "Options for the graph colors.")

    group.add_argument("--chromosome-box-color", type=str, default="#E5E5E5",
                       metavar="COLOR",
                       help=("The COLOR for the box surrounding even "
                             "chromosome numbers [Default: %(default)s]."))

    group.add_argument("--even-chromosome-color", type=str, default="#1874CD",
                       metavar="COLOR",
                       help=("The COLOR for the box surrounding even "
                             "chromosome numbers [Default: %(default)s]."))

    group.add_argument("--odd-chromosome-color", type=str, default="#4D4D4D",
                       metavar="COLOR",
                       help=("The COLOR for the box surrounding odd "
                             "chromosome numbers [Default: %(default)s]."))

    group.add_argument("--multipoint-color", type=str, default="#FF8C00",
                       metavar="COLOR",
                       help=("The COLOR for the multipoint plot [Default: "
                             "%(default)s]."))

    group.add_argument("--significant-color", type=str, default="#FF0000",
                       metavar="COLOR",
                       help=("The COLOR for points representing "
                             "significant linkage [Default: %(default)s]."))

    args = parser.parse_args()

    return args


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print >>sys.stderr, "Cancelled by user"
        sys.exit(0)
    except ProgramError as e:
        parser.error(e.message)